# Configuring ChurchBoard

Open `http://127.0.0.1:8040/admin`. Keep **Use demonstration data** enabled while learning the editor, then disable it before connecting production systems.

![ChurchBoard setup page](screenshots/setup.jpg)

## 1. Connect Planning Center

ChurchBoard currently uses a Planning Center Personal Access Token.

1. In Planning Center, open the developer Personal Access Token page for the account ChurchBoard should use.
2. Create a personal token and copy its **Application ID** and **Secret**.
3. In ChurchBoard Setup, enable **Planning Center** and paste both values.
4. Choose **Save & test connection**.
5. Check each service type ChurchBoard should consider.
6. Set the automatic plan window:
   - **Open days before** and **Open hours before** determine how early a plan becomes eligible.
   - **Close hours after** determines how long a plan stays eligible.
7. Choose **Save settings**.

The token user needs access to the selected Services plans. Services LIVE automation additionally requires permission to take control and advance the selected plan.

The service-type name and ID are saved together. If Planning Center temporarily cannot be reached, ChurchBoard retains the last saved display name instead of replacing it with a blank label.

## 2. Choose positions for a widget

1. From Setup, choose **Edit** for a dashboard.
2. Select a **Scheduled Positions & Mics** widget.
3. In the inspector, check the teams/categories to include, such as Band or Production.
4. Check the individual Planning Center positions to display.
5. Drag positions into the desired display order.
6. Save the dashboard.

Every selected position appears even when no person or microphone is assigned. An open Planning Center position displays **Unassigned**.

## 3. Add Shure microphones

ChurchBoard focuses on networked Shure QLX-D and ULX-D receivers.

1. Give each receiver a stable IP address or DHCP reservation.
2. In Setup, enable **Receiver monitoring**.
3. Choose **+ Add microphone**.
4. Enter a friendly mic name such as `Red`, the receiver IP, and channel.
5. Choose the Planning Center position that uses that mic.
6. Repeat for up to ten displayed microphones, then save.

The photo card and compact audio card use status borders:

- green: transmitter on with battery above 10%;
- yellow: transmitter on with 5–10% battery;
- red: transmitter off, receiver unreachable, or battery below 5%.

Deleting a microphone removes its receiver mapping only. It does not change Planning Center schedules.

## 4. Connect ProPresenter

1. In ProPresenter, enable the Network API.
2. Note the ProPresenter computer's local IP address and API port.
3. In ChurchBoard Setup, enable ProPresenter and enter both values.
4. Save settings.

In a ProPresenter widget, choose:

- **Text** or **Slide image** presentation;
- current slide, next slide, both, or neither;
- whether to show `Slide x of y`;
- item/playlist title and current/next part labels.

Part labels use their ProPresenter colors. Slide notes appear when enabled, and widget typography scales to keep long content visible.

## 5. Let ProPresenter drive Services LIVE

When ProPresenter is synced from a Planning Center plan, ChurchBoard can use the active presentation to control the corresponding Services LIVE item and timing.

1. Enable **Let ProPresenter drive Planning Center Services LIVE**.
2. Leave **Automatically take control when needed** enabled if ChurchBoard should claim LIVE control.
3. Leave **Prefer Planning Center song items for title matching** enabled.
4. Choose exact or smart fallback matching.
5. Set how long a presentation must remain active before ChurchBoard advances LIVE.

ChurchBoard first uses ProPresenter's Planning Center playlist/item ordering when available. It then uses normalized title matching, including non-song items such as `Message`, even when the presentation itself has a title like a Scripture reference.

## 6. Configure order of service

Select an **Order of service** widget in the editor to enable:

- scheduled item duration;
- estimated wall-clock start time;
- song/item leader;
- the leader's mapped microphone.

For multiple service times, ChurchBoard uses the active service instance. Before the day's first service or during an early rehearsal, estimates start from the earliest scheduled service time.

## 7. Configure team members

Add a **Team members** widget, select Planning Center teams/categories, then choose the positions to include. Each row can show a circular photo, name, and position. Names and positions scale together so longer entries remain visible.

## 8. Use a custom unassigned icon

A Scheduled Positions & Mics widget can replace the default `U` placeholder with media stored in the active Planning Center plan.

1. Add a PNG or JPEG as a Planning Center plan media item.
2. Give the media item a recognizable title, such as `Icon`.
3. Select the assignment widget in ChurchBoard's editor.
4. Enable the custom unassigned icon and enter that media title.
5. Save.

The title is configurable per widget, so different dashboards can use different plan-media icons. ChurchBoard matches the title without regard to capitalization.

## 9. Audio/SPL meter

Add an **Audio / SPL meter** widget and set the green, orange, and red thresholds. Choose **Enable microphone** from the display and grant the browser microphone permission. The permission button remains available at the widget's smallest size.

Browser microphone readings are useful as a production reference but are not a substitute for a calibrated, standards-compliant SPL meter. Calibration varies by computer, interface, browser, and microphone.

## 10. Open displays

Each dashboard has its own **Background color** picker at the top of the editor. The dashboard background, translucent liquid-glass widget surfaces, reflections, borders, and interface accents follow that color. Operational mic and SPL states remain green, yellow, or red so warnings are still immediately recognizable.

Use these default URLs locally:

```text
http://127.0.0.1:8040/display/main
http://127.0.0.1:8040/display/green-room
http://127.0.0.1:8040/display/audio
```

Substitute the ChurchBoard computer's IP address on other production-network devices. Use the fullscreen button in the top-right corner or the Raspberry Pi kiosk installer for a dedicated screen. The hamburger menu provides an **Edit** action beside each board. In the editor, **Open display** returns to that board in the same browser tab.

![WYSIWYG dashboard editor](screenshots/dashboard-editor.jpg)
