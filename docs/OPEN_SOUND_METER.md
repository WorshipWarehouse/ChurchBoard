# Open Sound Meter

ChurchBoard receives Open Sound Meter (OSM) Remote API level packets directly
on the production LAN. In OSM, open the Wi-Fi menu and enable **Remote API
Server**. ChurchBoard joins the multicast group `239.255.42.42:49007`, so the
OSM machine and ChurchBoard machine must be on the same multicast-enabled
network segment.

## Available live levels

The verified OSM `levels` message contains these values:

```json
{
  "api": "Open Sound Meter",
  "message": "levels",
  "data": {
    "A": {"Fast": -61.6, "Slow": -63.9},
    "B": {"Fast": -60.0, "Slow": -62.5},
    "C": {"Fast": -58.2, "Slow": -59.1},
    "Z": {"Fast": -57.7, "Slow": -61.0}
  }
}
```

These Remote API values use OSM's internal full-scale reference. OSM's own SPL
meter adds its fixed `140 dB` SPL offset when rendering them. ChurchBoard
applies the same conversion, so an API value of `-69` is displayed as `71 dB
SPL`, and values at or below the `-140` floor display as `0 dB SPL`.

In the Open Sound Meter widget settings, select A-, B-, C-, or Z-weighting and a
Fast or Slow response. The widget shows that exact live OSM value. In Setup,
choose the weighting and response used for downloadable service reports; that
selection is kept consistent for the entire report.

OSM broadcasts a separate `levels` packet for every active source. ChurchBoard
lists those sources by their OSM name in Setup. Select the same measurement
source you are viewing in OSM. Until a source is selected, ChurchBoard follows
the first OSM source it detects and does not switch based on the measured
level. Explicit selection is recommended whenever OSM has multiple sources.

The dashboard performs no smoothing, rolling average, peak hold, microphone
calibration, or automatic source selection on the live value. It displays the
chosen A/B/Z Fast/Slow field from the chosen source after applying only OSM's
own fixed SPL display reference described above. Historical averaging exists
only in downloaded service reports and never feeds the live widget.

## Service reports

When report recording is enabled, ChurchBoard correlates each selected OSM
level sample to the active Planning Center LIVE item. The Open Sound Meter
widget provides downloads for the service graph and per-item average CSV.

## RTA

OSM's verified multicast `levels` message does not include real-time-analysis
(RTA) spectrum bands. ChurchBoard therefore does not render an RTA from that
message. RTA support can be added later if OSM exposes and we capture a stable
multicast packet format for spectrum data.

The optional `tools/osm_bridge.py` helper remains useful for relaying OSM
levels to external WebSocket consumers, but ChurchBoard itself does not need it
for normal OSM monitoring.
