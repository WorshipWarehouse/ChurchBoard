# Security

## Intended deployment

ChurchBoard is intended for a trusted church production LAN. It listens on port `8040` so other production displays can connect, and it currently has no built-in user authentication or HTTPS termination.

Do not expose ChurchBoard directly to the public internet. Use network segmentation and firewall rules to restrict access to authorized production devices.

## Credentials

Planning Center Personal Access Token credentials are stored in ChurchBoard's local data file with owner-restricted permissions. The file is ignored by Git:

- source/development: `data/churchboard.json`
- Windows and macOS packaged app: `~/.churchboard/churchboard.json`
- Linux user installer and Raspberry Pi: the installer's `data` directory
- Debian package: `/var/lib/churchboard/churchboard.json`

Protect backups of those locations. Revoke the token in Planning Center if a ChurchBoard computer or backup is lost.

## Reporting a vulnerability

Do not open a public issue for a vulnerability that could expose credentials or control a production service. Contact the repository owner privately with a description, affected version, reproduction steps, and any proposed mitigation.
