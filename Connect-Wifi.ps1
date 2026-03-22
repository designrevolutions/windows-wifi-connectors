param
(
    # The Wi-Fi profile / SSID name that Windows already knows about.
    # This should match the saved Wi-Fi profile name used by netsh.
    [string]$WifiName = "Wifi Name",

    # Optional Wi-Fi interface name.
    # Example values:
    #   "Wi-Fi"
    #   "Wi-Fi 2"
    #
    # This is useful when a machine has more than one Wi-Fi adapter,
    # such as a failed onboard adapter plus a USB Wi-Fi dongle.
    #
    # Leave this empty to let netsh use its normal behaviour.
    [string]$InterfaceName = "",

    # Number of times to attempt the connection before giving up.
    [int]$MaxRetries = 3,

    # Number of seconds to wait between failed attempts.
    [int]$RetryDelaySeconds = 5,

    # Number of seconds to wait after issuing the connect command
    # before checking whether Windows actually connected.
    [int]$PostConnectWaitSeconds = 3
)

function Get-WifiInterfaceInfo
{
    <#
    .SYNOPSIS
        Read Wi-Fi interface information from 'netsh wlan show interfaces'.

    .DESCRIPTION
        The 'netsh' command returns plain text rather than structured objects.
        This function parses that text and builds a PowerShell object for each
        Wi-Fi interface that Windows reports.

        We intentionally capture:
        - Name
        - State
        - SSID

        This allows us to verify whether:
        - a specific adapter is connected
        - it is connected to the expected SSID

    .EXAMPLE
        $interfaces = Get-WifiInterfaceInfo
        $interfaces | Format-Table

    .NOTES
        Example output from netsh may look like:
            Name                   : Wi-Fi
            State                  : connected
            SSID                   : MyHomeWifi
    #>

    # Run the command and capture both standard output and standard error.
    $output = netsh wlan show interfaces 2>&1

    # This will hold the final list of parsed Wi-Fi interfaces.
    $interfaces = @()

    # Temporary hashtable used while parsing one interface block at a time.
    $current = @{}

    foreach ($line in $output)
    {
        # The start of a new interface block is usually identified by "Name : ..."
        if ($line -match '^\s*Name\s*:\s*(.+)$')
        {
            # If we were already building an interface object, store it before
            # starting the next one.
            if ($current.Count -gt 0)
            {
                $interfaces += [PSCustomObject]@{
                    Name  = $current["Name"]
                    State = $current["State"]
                    SSID  = $current["SSID"]
                }
            }

            # Start tracking the new interface.
            $current = @{
                Name  = $matches[1].Trim()
                State = $null
                SSID  = $null
            }

            continue
        }

        # Capture the interface state, for example:
        #   connected
        #   disconnected
        if ($line -match '^\s*State\s*:\s*(.+)$')
        {
            $current["State"] = $matches[1].Trim()
            continue
        }

        # Capture the SSID.
        # This intentionally matches "SSID" but not "BSSID".
        if ($line -match '^\s*SSID\s*:\s*(.+)$')
        {
            $current["SSID"] = $matches[1].Trim()
            continue
        }
    }

    # If the loop ended while we were still holding an interface block,
    # add it to the results.
    if ($current.Count -gt 0)
    {
        $interfaces += [PSCustomObject]@{
            Name  = $current["Name"]
            State = $current["State"]
            SSID  = $current["SSID"]
        }
    }

    return $interfaces
}

function Test-WifiConnected
{
    param
    (
        # The SSID we expect to be connected to.
        [string]$ExpectedSsid,

        # Optional interface name to restrict the check to one adapter only.
        [string]$ExpectedInterfaceName
    )

    <#
    .SYNOPSIS
        Check whether Wi-Fi is connected to the expected SSID.

    .DESCRIPTION
        This function does the important verification step that makes the
        script reliable.

        The original problem is that:
        - 'netsh wlan connect ...' can run successfully as a command
        - but that does NOT guarantee the Wi-Fi connection really succeeded

        So instead of trusting netsh, we ask Windows what the current Wi-Fi
        state actually is after the connection attempt.

        If an interface name is supplied, only that specific adapter is checked.
        This matters on machines with multiple Wi-Fi adapters.

    .EXAMPLE
        if (Test-WifiConnected -ExpectedSsid "OfficeWifi")
        {
            Write-Host "Connected"
        }

    .EXAMPLE
        if (Test-WifiConnected -ExpectedSsid "OfficeWifi" -ExpectedInterfaceName "Wi-Fi 2")
        {
            Write-Host "Connected on the USB dongle"
        }
    #>

    $interfaces = Get-WifiInterfaceInfo

    # If we could not read any Wi-Fi interface data, treat that as failure.
    if (-not $interfaces)
    {
        return $false
    }

    # If the caller supplied a specific interface name, filter to that one.
    if (-not [string]::IsNullOrWhiteSpace($ExpectedInterfaceName))
    {
        $interfaces = $interfaces | Where-Object {
            $_.Name -eq $ExpectedInterfaceName
        }
    }

    # Look for at least one interface that matches both:
    # - connected state
    # - expected SSID
    foreach ($interface in $interfaces)
    {
        if ($interface.State -match '^connected$' -and $interface.SSID -eq $ExpectedSsid)
        {
            return $true
        }
    }

    return $false
}

function Connect-WifiWithRetry
{
    param
    (
        # Target Wi-Fi profile / SSID to connect to.
        [string]$TargetWifiName,

        # Optional interface name such as "Wi-Fi 2".
        [string]$TargetInterfaceName,

        # Maximum number of attempts before giving up.
        [int]$RetryCount,

        # Seconds to wait between failed attempts.
        [int]$RetryDelay,

        # Seconds to wait after issuing the connect command before checking state.
        [int]$PostConnectWait
    )

    <#
    .SYNOPSIS
        Attempt to connect to Wi-Fi with retry logic.

    .DESCRIPTION
        This function wraps the plain netsh command with safer behaviour:

        1. Run the connection command
        2. Wait a short period for Windows to process the connection
        3. Check the real connection state
        4. Retry if needed

        This is more reliable than running netsh once and assuming success.

    .EXAMPLE
        Connect-WifiWithRetry `
            -TargetWifiName "OfficeWifi" `
            -TargetInterfaceName "Wi-Fi 2" `
            -RetryCount 3 `
            -RetryDelay 5 `
            -PostConnectWait 3
    #>

    for ($attempt = 1; $attempt -le $RetryCount; $attempt++)
    {
        Write-Host ""
        Write-Host "Attempt $attempt of $RetryCount to connect to '$TargetWifiName'..."

        # Build the netsh argument list.
        # Using an array here is cleaner and safer than constructing one big string.
        $netshArguments = @(
            "wlan"
            "connect"
            "name=$TargetWifiName"
        )

        # Add the interface argument only when one has been supplied.
        if (-not [string]::IsNullOrWhiteSpace($TargetInterfaceName))
        {
            $netshArguments += "interface=$TargetInterfaceName"
            Write-Host "Using interface '$TargetInterfaceName'."
        }

        # Run netsh and capture its output.
        # We still do NOT trust this output as proof of success.
        $connectOutput = & netsh @netshArguments 2>&1

        # Give Windows time to establish the connection.
        Start-Sleep -Seconds $PostConnectWait

        # This is the real success check.
        if (Test-WifiConnected -ExpectedSsid $TargetWifiName -ExpectedInterfaceName $TargetInterfaceName)
        {
            Write-Host "Successfully connected to '$TargetWifiName'."
            return $true
        }

        Write-Host "Connection attempt failed."

        # Print netsh output because it can sometimes contain useful hints,
        # such as profile not found or adapter issues.
        if ($connectOutput)
        {
            Write-Host "netsh output:"
            $connectOutput | ForEach-Object {
                Write-Host "  $_"
            }
        }

        # Only wait if another retry is still available.
        if ($attempt -lt $RetryCount)
        {
            Write-Host "Waiting $RetryDelay seconds before retrying..."
            Start-Sleep -Seconds $RetryDelay
        }
    }

    Write-Host "Failed to connect to '$TargetWifiName' after $RetryCount attempts."
    return $false
}

# Entry point for the script.
# This calls the main retry function using the script parameters defined at the top.
$success = Connect-WifiWithRetry `
    -TargetWifiName $WifiName `
    -TargetInterfaceName $InterfaceName `
    -RetryCount $MaxRetries `
    -RetryDelay $RetryDelaySeconds `
    -PostConnectWait $PostConnectWaitSeconds

# Return a process exit code so the script can be used in automation.
# 0 = success
# 1 = failure
if (-not $success)
{
    exit 1
}

exit 0
