# ChurchBoard legal information

This document is a practical project notice, not legal advice.

## License and ownership

ChurchBoard is distributed under the [MIT License](LICENSE). Third-party components retain their own licenses and copyright notices; see [Third-party notices](THIRD_PARTY_NOTICES.md).

The bundled demonstration portraits are AI-generated fictional sample people supplied by the project owner. They do not depict the named sample people or any intended real individual. They are included under the ChurchBoard project license for demonstration and documentation use.

## Credits and independence

ChurchBoard's visual microphone-monitoring direction was inspired by [Micboard](https://micboard.io/) by Karl Swanson. Micboard is an independent MIT-licensed project for visually monitoring network-enabled Shure devices. ChurchBoard is a separate implementation and does not bundle Micboard code or assets.

The initial cross-platform dashboard concept also drew inspiration from [NewsTalentMonitorPlus](https://github.com/wtapper89/NewsTalentMonitorPlus), an MIT-licensed project.

## Trademarks and third-party services

ChurchBoard is an independent project. It is not affiliated with, authorized by, sponsored by, or endorsed by Planning Center, Shure, Renewed Vision, ProPresenter, Micboard, Apple, Microsoft, or the Raspberry Pi Foundation.

Planning Center, Shure, QLX-D, ULX-D, Renewed Vision, ProPresenter, Apple, macOS, Mac, Microsoft, Windows, and Raspberry Pi are trademarks or registered trademarks of their respective owners. Their names are used only to identify compatible products or services.

Use of third-party APIs, devices, accounts, media, and services remains subject to the applicable owner's terms, licenses, privacy policies, permissions, and rate limits. Users are responsible for obtaining permission to display Planning Center profile photos or other personal data on ChurchBoard screens.

## Privacy and network exposure

ChurchBoard processes Planning Center credentials, schedule data, names, and photos locally on the ChurchBoard computer. It does not provide its own cloud service. The local dashboard server currently has no built-in authentication or TLS; follow [SECURITY.md](SECURITY.md) and keep it on a trusted, access-controlled production network.

## Operational and SPL limitations

Mic telemetry, service timing, slide matching, and control status are informational. Confirm critical production actions in the manufacturers' or service providers' official interfaces. Do not use ChurchBoard as the sole indication for safety-critical, emergency, hearing-protection, or regulatory decisions.

The browser Audio/SPL widget is an approximate production reference whose response varies by microphone, interface, operating system, browser, placement, and calibration. It is not a certified sound-level meter or noise dosimeter and is not intended for regulatory compliance. Use a properly calibrated, standards-compliant instrument and qualified guidance for occupational or hearing-safety measurements.
