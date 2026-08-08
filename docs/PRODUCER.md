# Producer workspace beta

ChurchBoard 1.4 evolves the display system into a service-production workspace. This beta implements the first usable slices of GitHub issues #2, #5, #26, and #28 while retaining the existing local, no-login behavior until an owner account is created.

## Start the beta

Open `/producer` on the ChurchBoard computer. On first use, ChurchBoard asks you to create the organization owner. Creating that account enables authentication for protected setup, editor, and producer pages.

Roles are intentionally simple:

- **Admin** manages users, campuses, integrations, layouts, checklist definitions, and resources.
- **Editor** manages layouts, checklist definitions, resources, and the live service workflow.
- **Volunteer** sees the work and resources for their own Planning Center person/positions and can complete assigned checklist tasks.

The owner chooses whether ChurchBoard accounts require passwords under **Producer → Team → Sign-in security**. With passwords off, the login page is a simple account chooser; this is convenient for a physically controlled production network but provides no protection against another person on that network. With passwords on, users sign in using email and password. ChurchBoard stores a salted PBKDF2 hash, not the original password. Sessions use HTTP-only cookies and become Secure when ChurchBoard is served over HTTPS.

If an administrator loses their credentials, open `/login` directly on the computer running ChurchBoard and choose **Lost administrator credentials?**. Enter the administrator email and a new password. Recovery is limited to loopback access and turns password sign-in back on.

## Campuses, users, and Planning Center positions

An admin can create, edit, or delete campuses and users from **Producer → Team**. A campus represents a physical church location and scopes its users, checklists, and resources. A single-location church can keep only **Main Campus** and otherwise ignore this feature. Deleting a campus moves its assigned users and producer content to the first remaining campus.

For volunteers, choose their name from the **Planning Center person** list or use **Match by name or email**. ChurchBoard stores Planning Center's internal link behind the scenes and then scopes the volunteer's work to that scheduled person. The raw person ID is no longer required in the interface.

The active service chooser at the top of Producer lists all plans currently returned by the configured Planning Center service types. Select a dated plan to lock ChurchBoard to it, or choose **Automatic service selection** to use the configured open/close timing window.

Checklist templates use the position keys returned by the configured Planning Center Services plan. A template can therefore follow whoever is scheduled as `Band · Vox 1`, `Production · Audio`, or another selected position instead of being tied permanently to one person.

## Position checklists and resources

From **Producer → Checklists & resources**, name the checklist, choose its campus and Planning Center positions, add required or optional tasks, and save. Editing a template creates a new version so changes do not silently rewrite the definition used by earlier services. The Service tab combines the selected plan, scheduled people, matching templates, and per-service completion state. Activity records identify who changed each task and when.

Editors can also attach a link or upload a PDF, image, video, or document and associate it with positions and a campus. Uploaded files are kept beneath ChurchBoard's local data directory. Do not upload confidential material unless the host, backups, accounts, and network are secured appropriately.

## Portable layouts and widget editing

Use **Export layouts** from the desktop control page to back up all dashboards, or export the open layout from its editor. **Import layout** validates the file before storing it; a conflicting slug or name is preserved by assigning the imported dashboard a new one. Treat exports as configuration files and review operational details before sharing them.

The editor palette groups widgets into Service & timing, Planning Center, ProPresenter, Audio & streaming, and Content. Search filters the list. Right-click a widget on the canvas to edit, duplicate, or remove it. On a touch device, use the selected-widget inspector and action buttons.

## HTTPS

Direct TLS is enabled by supplying both environment variables before ChurchBoard starts:

```bash
export CHURCHBOARD_SSL_CERTFILE=/absolute/path/to/fullchain.pem
export CHURCHBOARD_SSL_KEYFILE=/absolute/path/to/private-key.pem
python run.py --background
```

ChurchBoard then listens at `https://<host>:8040`. The certificate must include the hostname used by phones and tablets. A publicly trusted certificate avoids browser warnings; with an internal certificate authority, install that authority on every client. Never commit private keys. A maintained reverse proxy may terminate HTTPS instead. Authentication is not a substitute for firewalling: expose only the required port to the trusted production or staff network.

## Mobile use

On the same trusted network, open `https://churchboard-hostname:8040/producer` from a phone or tablet. Producer navigation, scheduled-person cards, checklists, forms, and editor chrome collapse to touch-friendly single-column layouts. Dashboard content still follows each saved grid, so create a dedicated narrow board for a curated phone display.

## Beta limits

This release uses local accounts. Invitation email, password-reset email, SSO, directory synchronization, aggregate reporting, and cloud storage remain future work. Back up the ChurchBoard data directory and export layouts before substantial testing.
