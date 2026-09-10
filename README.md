# SSSRCL
IBM Spectrum Scale System — Remote Code Load Container Manager

Hosts the **RCL (Remote Code Load) service container** on an IBM Utility BareMetal node (5149-23E).
The RCL container opens an outbound SSH tunnel to the IBM Service Portal, allowing IBM service engineers to reach the ESS nodes without requiring inbound firewall rules on the customer side.

> **Note:** `SSSRCL`, `SSSAPI`, and `SSSDEPLOYGUI` have been unified into the [SSSMANAGER](https://github.ibm.com/IBMSpectrumScale/SSSMANAGER) repository. Use `SSSMANAGER` for all new deployments. This repository is maintained for standalone use only.

---

## Quick start

```bash
./startRCLContainer
```

This is the **only script you need to run**. It auto-detects system settings, writes a sanitised `rclmgr.yml`, and starts the container.

---

## Usage

```text
./startRCLContainer [options]

Options:
  -d, --delete                   Delete the RCL service container and its systemd service unit.
  -v, --verbose                  Display verbose messages in the console.

  Install source (mutually exclusive):
  -f,  --file-name FILE          Restore the container from a local tar file.
                                 (default: SSSRCL.tar)
  -vn, --image-version VER       RCL container image version to deploy.
                                 (default: 7.0.2.0)

  Options (start only, not valid with -d/--delete):
  -i,  --campus-interface IF     Name of the interface connected to the campus
                                 network. (default: campus)
```

### Examples

```bash
# Start using the default settings (pulls image from IBM registry)
./startRCLContainer

# Start from a local tarball
./startRCLContainer -f SSSRCL.tar

# Override the image version
./startRCLContainer -vn 7.0.1.1

# Override the campus interface
./startRCLContainer -vn 7.0.2.0 -i eth0

# Verbose output
./startRCLContainer -v

# Delete the container
./startRCLContainer -d
```

---

## Prerequisites

### OS and software

- RHEL / Red Hat compatible Linux
- `podman` installed and accessible
- `nmcli` installed and accessible
- User-level systemd lingering enabled (`loginctl enable-linger`)

### Network interfaces

| Interface | Purpose |
|-----------|---------|
| `campus`  | Public network — connects the Utility host to the Internet for the IBM Service Portal SSH tunnel |
| `virbr1`  | RAS bridge — internal communication with EMSVM |

The `campus` interface must have a public IP, a proper gateway, and DNS resolution configured.

### OS user

Create the `rcladmin` user before running the script:

```bash
sudo useradd rcladmin
sudo passwd rcladmin
```

Copy the sudoers file:

```bash
sudo cp rcladmin_sudoers /etc/sudoers.d/rcladmin_sudoers
sudo chmod 440 /etc/sudoers.d/rcladmin_sudoers
```

### Hosts file

Replace `/etc/hosts` with the provided template (or append its contents):

```bash
sudo cp utilityBareMetal_hosts /etc/hosts
```

Ensure the RAS IP for EMSVM (`10.23.16.2 emsvm`) is correct for your system.

### IBM Container Registry login

```bash
podman login cp.icr.io --username cp --password <API_Key>
```

The RCL image is pulled from:

```
preprod.icr.io/cp/scale-devops/scalesystem/sss_rcl
```

---

## Configuration

`rclmgr.yml` is written automatically by `startRCLContainer`. You can also edit it manually for advanced settings:

```yaml
CONTAINER:
    CONTAINER_HOSTNAME: utilityBareMetal-rcl-official
    CONTAINER_DOMAIN_NAME: gpfs.local

    UTILITY_HOSTNAME: utilityBareMetal

    CAMPUS_INTERFACE: campus
    CAMPUS_INTERFACE_IP: 9.114.12.77   # ← auto-detected at runtime

    RAS_INTERFACE: virbr1
    RAS_INTERFACE_IP: 10.23.16.1

    SSH_PORT: 10022                    # IBM Service Portal SSH port

    IMAGE_NAME: preprod.icr.io/cp/scale-devops/scalesystem/sss_rcl
    IMAGE_VERSION: 7.0.2.0

    LOG:  /home/rcladmin/log
    BKUP: /home/rcladmin/backup
```

> `CAMPUS_INTERFACE_IP` is auto-detected from the campus interface at runtime. The value in the YAML is used as a fallback only.

---

## Port reference

| Host port | Container port | Purpose |
|-----------|----------------|---------|
| 10022     | 22             | SSH tunnel to IBM Service Portal |

---

## Systemd service

After a successful start the container is registered as a user-level systemd service that auto-starts on login:

```bash
# Check status
systemctl --user status container-utilityBareMetal-rcl-official.service

# Start / stop
systemctl --user start  container-utilityBareMetal-rcl-official.service
systemctl --user stop   container-utilityBareMetal-rcl-official.service
```

---

## Logs

Local execution logs are written to `./logs/` and are also copied to `/var/log/rcl/startRCLContainer/` if that directory exists.

---

## Project structure

```text
SSSRCL/
├── startRCLContainer        ← entry point (run this)
├── rclmgr.yml               ← configuration file (auto-generated / editable)
├── rclmgr                   ← legacy low-level manager (deprecated, use startRCLContainer)
├── rcladmin_sudoers          ← sudoers entry for rcladmin
├── utilityBareMetal_hosts   ← /etc/hosts template for the Utility node
└── classes/
    └── rclmgr_yml.py        ← config + container lifecycle class
```

---

## IBM Service Portal

Once the container is running, the IBM Utility host appears in the IBM Service Portal. Log in at:

- https://rsc1.tms.stglabs.ibm.com/
- https://rsc2.tms.stglabs.ibm.com/
- https://rsc3.tms.stglabs.ibm.com/

Use your IBM Intranet ID to authenticate. Click **View all connected ESS systems** to find the registered node, then click **Start Terminal** to open an SSH tunnel into the service container.

Default service container users:

| User       | Role |
|------------|------|
| `rcladmin` | Power user — can deploy and update SSS nodes |
| `rcluser`  | Read-only — can view node health, cannot deploy |

Default password for both users: `cluster` (change after first login).

---

## Related repositories

| Repository | Purpose |
|------------|---------|
| [SSSMANAGER](https://github.ibm.com/IBMSpectrumScale/SSSMANAGER) | Unified manager for RCL + API + Deploy GUI |
| [SSSAPI](https://github.ibm.com/IBMSpectrumScale/SSSAPI) | SSS API Server container manager |
| [SSSDEPLOYGUI](https://github.ibm.com/IBMSpectrumScale/SSSDEPLOYGUI) | Deploy from GUI container manager |
