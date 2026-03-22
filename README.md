# Wi-Fi Connect Retry Scripts

This repository contains two small Windows utilities for connecting to Wi-Fi more reliably:

* `Connect-Wifi.ps1` → PowerShell version
* `connect_wifi.py` → Python version

---

## Why I made this

I had trouble connecting to Wi-Fi on one of my laptops.

That laptop needs to connect to different Wi-Fi networks, and its onboard Wi-Fi had failed, so I am using a USB Wi-Fi dongle instead.

I started by using the standard command:

```powershell
netsh wlan connect name="My Wifi"
```

This worked **sometimes**, but it had a major flaw:

* The command itself would run successfully
* But the Wi-Fi connection would **not actually be established**
* There was **no reliable way to detect failure**

So scripts using `netsh` alone would:

* appear to succeed
* but silently fail to connect

That made it unsuitable for automation.

---

## What this repo solves

These scripts wrap `netsh` with **real verification + retry logic**.

Instead of trusting the command, they:

1. Attempt the connection using `netsh`
2. Wait a short period
3. Query Windows for actual Wi-Fi state
4. Verify:

   * the interface is **connected**
   * the SSID matches the expected network
5. Retry if needed

---

## Key Features

* Reliable connection verification (not just command success)
* Retry logic with configurable delays
* Optional Wi-Fi adapter selection (important for USB dongles)
* Works with multiple adapters
* Returns proper exit codes (0 = success, 1 = failure)
* Designed for automation and scripting

---

## Quick Start

### PowerShell (recommended for quick use)

```powershell
.\Connect-Wifi.ps1 -WifiName "My Wifi"
```

Specify a Wi-Fi adapter:

```powershell
.\Connect-Wifi.ps1 -WifiName "My Wifi" -InterfaceName "Wi-Fi 2"
```

Full example:

```powershell
.\Connect-Wifi.ps1 `
    -WifiName "My Wifi" `
    -InterfaceName "Wi-Fi 2" `
    -MaxRetries 3 `
    -RetryDelaySeconds 5 `
    -PostConnectWaitSeconds 3
```

---

### Python

Edit the values at the bottom of the script:

```python
wifi_name = "My Wifi"
wifi_interface_name = "Wi-Fi 2"  # Set to None if not needed
```

Run:

```bash
python connect_wifi.py
```

---

## File Overview

### `Connect-Wifi.ps1`

PowerShell implementation.

Best for:

* Windows-only usage
* quick scripting
* automation tasks

---

### `connect_wifi.py`

Python implementation.

Best for:

* extending into larger tools
* adding logging / config files
* integrating into Python workflows

---

## How it works (important)

The key design principle:

❌ Do NOT trust `netsh wlan connect`
✅ Always verify actual connection state

The scripts use:

```powershell
netsh wlan show interfaces
```

They parse:

* Interface Name
* State (connected / disconnected)
* SSID

A connection is only considered successful if:

* State = `connected`
* SSID = expected Wi-Fi name
* (Optional) Interface matches the specified adapter

---

## Using a specific Wi-Fi adapter (USB dongle scenario)

Example:

```powershell
netsh wlan connect name="My Wifi" interface="Wi-Fi 2"
```

Supported via:

* PowerShell → `-InterfaceName`
* Python → `interface_name`

---

## Finding your adapter name

Run:

```powershell
netsh wlan show interfaces
```

Example:

```text
Name                   : Wi-Fi
Name                   : Wi-Fi 2
```

Use the exact value.

---

## PowerShell Usage (Detailed)

### Parameters

| Parameter                 | Description               |
| ------------------------- | ------------------------- |
| `-WifiName`               | Wi-Fi profile / SSID      |
| `-InterfaceName`          | Optional adapter          |
| `-MaxRetries`             | Retry attempts            |
| `-RetryDelaySeconds`      | Delay between retries     |
| `-PostConnectWaitSeconds` | Delay before verification |

---

### Examples

```powershell
.\Connect-Wifi.ps1 -WifiName "Office Wifi"
```

```powershell
.\Connect-Wifi.ps1 -WifiName "Office Wifi" -InterfaceName "Wi-Fi 2"
```

```powershell
.\Connect-Wifi.ps1 `
    -WifiName "Office Wifi" `
    -InterfaceName "Wi-Fi 2" `
    -MaxRetries 5 `
    -RetryDelaySeconds 10 `
    -PostConnectWaitSeconds 4
```

---

## Python Usage (Detailed)

### Basic

Edit:

```python
wifi_name = "My Wifi"
wifi_interface_name = "Wi-Fi 2"
```

Run:

```bash
python connect_wifi.py
```

---

### Example config block

```python
wifi_name = "Office Wifi"
wifi_interface_name = "Wi-Fi 2"

was_successful = connect_to_wifi_with_retries(
    target_ssid=wifi_name,
    interface_name=wifi_interface_name,
    max_retries=3,
    retry_delay_seconds=5,
    post_connect_wait_seconds=3
)
```

---

### Import into another script

```python
from connect_wifi import connect_to_wifi_with_retries

success = connect_to_wifi_with_retries(
    target_ssid="Office Wifi",
    interface_name="Wi-Fi 2",
    max_retries=3,
    retry_delay_seconds=5,
    post_connect_wait_seconds=3
)

print(success)
```

---

## Example underlying netsh commands

```powershell
netsh wlan connect name="My Wifi"
```

```powershell
netsh wlan connect name="My Wifi" interface="Wi-Fi 2"
```

---

## Requirements

### PowerShell

* Windows
* PowerShell
* `netsh`

### Python

* Windows
* Python 3.9+
* `netsh`

---

## Exit Codes

| Code | Meaning |
| ---- | ------- |
| 0    | Success |
| 1    | Failure |

---

## Limitations

* Wi-Fi profile missing
* adapter disabled
* incorrect adapter name
* network out of range
* incorrect credentials
* unstable USB dongle

---

## Future Improvements

* Validate adapter exists
* Validate Wi-Fi profile exists
* Add logging
* Add better error classification
* Add CLI args to Python
* Add adapter reset logic

---

## Summary

This project exists because:

`netsh wlan connect` is not reliable on its own.

These scripts fix that by adding:

* verification
* retry logic
* adapter targeting

Making Wi-Fi automation **actually dependable**.
