import re
import subprocess
import time
from typing import Optional


def run_command(command: list[str]) -> tuple[int, str, str]:
    """
    Run a system command and return:
    - exit code
    - stdout
    - stderr

    We capture all three because they are useful for:
    - debugging
    - logging
    - showing useful messages when a connection attempt fails

    Important:
        For this specific use case, we do NOT fully trust the netsh exit code
        to tell us whether the Wi-Fi connection actually succeeded.

    Example:
        code, stdout, stderr = run_command(
            ["netsh", "wlan", "show", "interfaces"]
        )
    """
    completed_process = subprocess.run(
        command,
        capture_output=True,
        text=True,
        shell=False
    )

    return (
        completed_process.returncode,
        completed_process.stdout,
        completed_process.stderr
    )


def get_wifi_interfaces() -> list[dict[str, Optional[str]]]:
    """
    Read all Wi-Fi interfaces using:
        netsh wlan show interfaces

    Returns:
        A list of dictionaries containing:
        - name
        - state
        - ssid

    Why this exists:
        The 'netsh wlan connect ...' command alone is not enough for reliable
        automation because the command itself may run successfully while the
        actual Wi-Fi connection does not get established.

        So after a connection attempt, we read the real interface state from
        Windows and verify whether the correct adapter is connected to the
        correct SSID.

    Example:
        interfaces = get_wifi_interfaces()

        for interface in interfaces:
            print(interface)

    Example returned data:
        [
            {
                "name": "Wi-Fi",
                "state": "connected",
                "ssid": "MyHomeWifi"
            },
            {
                "name": "Wi-Fi 2",
                "state": "disconnected",
                "ssid": None
            }
        ]
    """
    _, stdout, stderr = run_command(["netsh", "wlan", "show", "interfaces"])

    # Prefer stdout, but fall back to stderr if needed.
    raw_output = stdout if stdout else stderr

    interfaces: list[dict[str, Optional[str]]] = []
    current_interface: Optional[dict[str, Optional[str]]] = None

    # Parse the plain text output one line at a time.
    for line in raw_output.splitlines():
        # Start of a new interface block.
        name_match = re.match(r"^\s*Name\s*:\s*(.+)$", line)
        if name_match:
            # Save the previous interface before starting a new one.
            if current_interface is not None:
                interfaces.append(current_interface)

            current_interface = {
                "name": name_match.group(1).strip(),
                "state": None,
                "ssid": None
            }
            continue

        # Ignore lines until we have found the first interface block.
        if current_interface is None:
            continue

        # Capture the state, such as:
        #   connected
        #   disconnected
        state_match = re.match(r"^\s*State\s*:\s*(.+)$", line)
        if state_match:
            current_interface["state"] = state_match.group(1).strip()
            continue

        # Capture the SSID.
        # This pattern matches "SSID" but not "BSSID".
        ssid_match = re.match(r"^\s*SSID\s*:\s*(.+)$", line)
        if ssid_match:
            current_interface["ssid"] = ssid_match.group(1).strip()
            continue

    # Add the final interface block if one was being built.
    if current_interface is not None:
        interfaces.append(current_interface)

    return interfaces


def is_connected_to_target(
    target_ssid: str,
    interface_name: Optional[str] = None
) -> bool:
    """
    Check whether Windows is currently connected to the target SSID.

    Args:
        target_ssid:
            The Wi-Fi profile / SSID that we expect to be connected.
        interface_name:
            Optional adapter name, for example:
                "Wi-Fi"
                "Wi-Fi 2"

            If supplied, only that specific adapter is checked.
            This is especially useful when a laptop has:
            - a failed onboard Wi-Fi adapter
            - a USB Wi-Fi dongle being used instead

    Returns:
        True if connected as expected, otherwise False.

    Why this matters:
        This is the verification step that makes the script reliable.
        We do not trust the netsh connect command on its own.

    Example:
        if is_connected_to_target("Office Wifi"):
            print("Connected")

        if is_connected_to_target("Office Wifi", "Wi-Fi 2"):
            print("Connected using the USB Wi-Fi dongle")
    """
    interfaces = get_wifi_interfaces()

    # If an interface name is supplied, restrict the check to that one.
    if interface_name:
        interfaces = [
            interface
            for interface in interfaces
            if interface["name"] == interface_name
        ]

    # Success means:
    # - the interface state is connected
    # - the SSID matches the target SSID
    for interface in interfaces:
        state = interface.get("state")
        ssid = interface.get("ssid")

        if state and state.lower() == "connected" and ssid == target_ssid:
            return True

    return False


def connect_to_wifi(
    target_ssid: str,
    interface_name: Optional[str] = None
) -> tuple[int, str, str]:
    """
    Attempt to connect to a Wi-Fi profile using netsh.

    Args:
        target_ssid:
            The saved Windows Wi-Fi profile name.
        interface_name:
            Optional adapter name. If supplied, netsh will attempt to use
            that specific Wi-Fi interface.

    Returns:
        A tuple of:
        - return code
        - stdout
        - stderr

    Important:
        The result from this function is not treated as final proof that the
        connection worked. The caller should verify the actual connection
        state afterwards.

    Example:
        code, stdout, stderr = connect_to_wifi(
            "My Wifi",
            interface_name="Wi-Fi 2"
        )
    """
    command = [
        "netsh",
        "wlan",
        "connect",
        f"name={target_ssid}"
    ]

    # Only add the interface argument if one was supplied.
    if interface_name:
        command.append(f"interface={interface_name}")

    return run_command(command)


def connect_to_wifi_with_retries(
    target_ssid: str,
    interface_name: Optional[str] = None,
    max_retries: int = 3,
    retry_delay_seconds: int = 5,
    post_connect_wait_seconds: int = 3
) -> bool:
    """
    Attempt to connect to a Wi-Fi network, retrying when needed.

    Args:
        target_ssid:
            The Wi-Fi profile / SSID to connect to.
        interface_name:
            Optional interface name such as "Wi-Fi 2".
        max_retries:
            Maximum number of attempts before giving up.
        retry_delay_seconds:
            How long to wait between failed attempts.
        post_connect_wait_seconds:
            How long to wait after issuing the connect command before
            checking Windows for the real connection state.

    Returns:
        True if the connection succeeds, otherwise False.

    Why this function exists:
        This is the wrapper that turns a plain netsh command into something
        more suitable for automation.

        Instead of assuming that the command worked, it:
        1. runs the command
        2. waits briefly
        3. checks the real Wi-Fi state
        4. retries if needed

    Example:
        success = connect_to_wifi_with_retries(
            target_ssid="My Wifi",
            interface_name="Wi-Fi 2",
            max_retries=3,
            retry_delay_seconds=5,
            post_connect_wait_seconds=3
        )

        if success:
            print("Connection successful")
        else:
            print("Connection failed")
    """
    for attempt_number in range(1, max_retries + 1):
        print()
        print(
            f"Attempt {attempt_number} of {max_retries} "
            f"to connect to '{target_ssid}'..."
        )

        if interface_name:
            print(f"Using interface '{interface_name}'.")

        # Ask netsh to connect to the Wi-Fi profile.
        return_code, stdout, stderr = connect_to_wifi(
            target_ssid=target_ssid,
            interface_name=interface_name
        )

        # Allow time for Windows to complete the connection attempt.
        time.sleep(post_connect_wait_seconds)

        # This is the real success check.
        if is_connected_to_target(
            target_ssid=target_ssid,
            interface_name=interface_name
        ):
            print(f"Successfully connected to '{target_ssid}'.")
            return True

        print("Connection attempt failed.")

        # Show the raw netsh output because it may contain a useful hint.
        if stdout.strip():
            print("netsh stdout:")
            print(stdout.strip())

        if stderr.strip():
            print("netsh stderr:")
            print(stderr.strip())

        print(f"netsh return code: {return_code}")

        # Only pause if we still have another retry available.
        if attempt_number < max_retries:
            print(f"Waiting {retry_delay_seconds} seconds before retrying...")
            time.sleep(retry_delay_seconds)

    print(f"Failed to connect to '{target_ssid}' after {max_retries} attempts.")
    return False


if __name__ == "__main__":
    """
    Example entry point for manual testing.

    Update the values below to match your environment.

    Notes:
        - 'wifi_name' should match a saved Windows Wi-Fi profile.
        - 'wifi_interface_name' can be set to None if you do not want to
          target a specific adapter.
        - If you are using a USB Wi-Fi dongle, this may be something like
          'Wi-Fi 2'.

    Example:
        python connect_wifi.py
    """
    wifi_name = "Wifi Name"
    wifi_interface_name = "Wi-Fi 2"  # Set to None if not needed.

    was_successful = connect_to_wifi_with_retries(
        target_ssid=wifi_name,
        interface_name=wifi_interface_name,
        max_retries=3,
        retry_delay_seconds=5,
        post_connect_wait_seconds=3
    )

    raise SystemExit(0 if was_successful else 1)
