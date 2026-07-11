# Wazuh `override.conf` Files

## Purpose

This archive contains two `systemd` override files created for Kevin's
Ubuntu 24.04.1 Wazuh All-in-One server after upgrading from Wazuh 4.14.2
to 4.14.6.

These overrides resolve a startup dependency issue where the Wazuh
Dashboard and Wazuh Manager could start before the Wazuh Indexer was
fully initialized after a system reboot.

The result is a more reliable boot sequence and fewer startup connection
errors.

## ZIP Contents

    wazuh-manager.service.d/
    └── override.conf

    wazuh-dashboard.service.d/
    └── override.conf

### wazuh-manager.service.d/override.conf

Ensures the Wazuh Manager waits for the Wazuh Indexer before starting.

Configuration:

``` ini
[Unit]
Requires=wazuh-indexer.service
After=wazuh-indexer.service

[Service]
TimeoutStartSec=300
```

### wazuh-dashboard.service.d/override.conf

Ensures the Wazuh Dashboard waits until both the Wazuh Indexer and Wazuh
Manager are running before starting.

Configuration:

``` ini
[Unit]
Requires=wazuh-indexer.service wazuh-manager.service
After=wazuh-indexer.service wazuh-manager.service
```

## Installation

1.  Copy each override.conf into its corresponding service override
    directory under `/etc/systemd/system/`.
2.  If the directory does not exist, create it.
3.  Reload systemd:

``` bash
sudo systemctl daemon-reload
```

4.  Reboot or restart the affected services.

## Benefits

-   Prevents startup race conditions.
-   Allows the Indexer additional initialization time.
-   Reduces Dashboard connection errors after reboot.
-   Provides a more reliable unattended startup sequence.
-   Recommended as part of the baseline build for this SOC lab.

## Tested Environment

-   Ubuntu 24.04.1 LTS
-   Wazuh All-in-One
-   Wazuh 4.14.6
-   Single-node Indexer
-   VMware virtual machine

Author: Kevin
