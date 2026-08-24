# Waste Collection Ecoservice Lithuania

Waste Collection Ecoservice Lithuania is a Home Assistant custom integration for scheduled waste collections in Lithuania. During initial setup it uses the [Ecoservice schedules page](https://ecoservice.lt/grafikai/) only to find container inventory numbers. After setup, collection calendars, history, weights, and payable invoices are retrieved exclusively from the VASA self-service portal.

> [!IMPORTANT]
> This is an unofficial community integration. It is not affiliated with, endorsed by, or supported by Ecoservice, VASA, Microsoft, or Home Assistant.

## Features

- UI-based setup with searchable municipality and address selectors.
- Prefix address filtering after the first three entered characters and a naturally sorted A–Z list when the field is empty.
- Selection of one or more containers associated with an address.
- An enabled-by-default calendar containing all scheduled collection dates.
- A nearest-collection date sensor and separate next-collection sensors for each supported waste type.
- A days-until-collection sensor for every selected container.
- A diagnostic VASA connection status.
- VASA sensors for the latest collection date, latest collected weight, yearly weight, and payable amount.
- Upcoming dates from each selected container's own VASA calendar.
- Hourly refresh while source data is incomplete, then daily refresh, with local caching of the last successfully retrieved data.
- English and Lithuanian configuration-flow translations.

Supported country: **Lithuania (`LT`)**.

## Waste-type codes

The letter in an inventory number identifies the waste type:

| Code | Waste type |
| --- | --- |
| `L` | Mixed/general waste |
| `P` | Paper waste |
| `S` | Glass waste |

## Installation

### HACS custom repository

Until this integration is accepted into the default HACS catalog:

1. Open HACS in Home Assistant.
2. Select **Integrations**, open the three-dot menu, and choose **Custom repositories**.
3. Add `https://github.com/kubickasa/ecoservice_waste_collection` with category **Integration**.
4. Find **Waste Collection Ecoservice Lithuania** and install it.
5. Restart Home Assistant.

After acceptance into the default HACS catalog, search for **Waste Collection Ecoservice Lithuania** directly in HACS; adding a custom repository will no longer be necessary.

### Manual installation

1. Download the latest GitHub Release.
2. Copy `custom_components/ecoservice_waste_collection` into the `custom_components` directory in your Home Assistant configuration.
3. Confirm that this file exists:

   ```text
   /config/custom_components/ecoservice_waste_collection/manifest.json
   ```

4. Restart Home Assistant.

## Configuration

Configure the integration entirely through the Home Assistant UI:

1. Go to **Settings → Devices & services** and select **Add integration**.

   ![Open Devices and services](docs/images/setup/01-settings-devices-services.png)

2. Select **Add integration**.

   ![Select Add integration](docs/images/setup/02-add-integration.png)

3. Search for and select **Waste Collection Ecoservice Lithuania**.

   ![Search for the Ecoservice integration](docs/images/setup/03-search-ecoservice.png)

4. Start typing a municipality name and select an exact suggestion, or leave the field empty to browse the list.

   ![Select a municipality](docs/images/setup/04-select-municipality.png)

5. Open the address selector. Enter at least the first three characters to filter addresses by the beginning of the address, or leave it empty to browse the naturally sorted A–Z list.

   ![Enter the start of an address](docs/images/setup/05-enter-address.png)

6. Select the exact address and continue.

   ![Submit the selected address](docs/images/setup/06-submit-address.png)

7. Select one or more containers. Ecoservice is used only through this step to obtain their inventory numbers.
8. Enter the required VASA username and password. All subsequent updates use VASA only.

The integration uses one config entry per municipality/address pair. Open **Configure** on the integration entry to update the selected inventory numbers or VASA credentials later.

## Calendar and sensors

The integration creates one device for the selected address and exposes:

- **Waste collection calendar** — enabled and visible by default; contains all-day events for the selected containers. Its state represents whether an event is currently active, so `off` is normal when no collection is taking place today. Upcoming entries are available through the calendar API and the `upcoming_events` attribute.
- **Next waste collection** — the earliest upcoming date across all selected containers.
- **Next paper collection**, **Next glass collection**, and **Next mixed-waste collection** — the next date for each waste type.
- One **Days until collection** sensor for each selected container. Attributes include the next date, up to ten upcoming dates, municipality, address, inventory number, waste type, source, and last successful update.

The integration also creates:

- A latest successful collection date and latest collected weight sensor for each of paper, glass, and mixed waste.
- A latest service-attempt status for each waste type, including unsuccessful-service reasons such as a container not being put out.
- A current-year collected weight sensor for each supported waste type.
- A latest actual collection summary sensor.
- A payable amount sensor in EUR, with individual invoice numbers and amounts in its attributes.

The diagnostic entities show VASA status:

- **VASA connection** reports whether at least one VASA data endpoint succeeded. Its attributes show history and billing endpoint states separately. Expired VASA access tokens are renewed automatically once before a request is marked failed.
- **Last update from VASA** shows when VASA data was last retrieved successfully and applied to Home Assistant. The timestamp survives restarts and remains visible during connection failures.

The integration retries every hour until every selected container has an upcoming VASA collection date and both VASA history and billing requests succeed. Once those conditions are met, it returns to the normal 24-hour interval. A genuinely absent collection or weight record does not keep the integration in hourly retry mode.
- Up to 100 locally cached collection-history records per selected container.

Exact entity IDs are assigned by Home Assistant and may include an address or device prefix. Unique IDs remain stable for a config entry.

## Data refresh

VASA data is refreshed every **24 hours**, or every hour while required data is incomplete. A manual entity update or integration reload can request an earlier refresh. The last successfully retrieved VASA results are stored in Home Assistant's local storage and retained when VASA is temporarily unavailable.

The public Microsoft Power BI Publish-to-web report used by the Ecoservice schedules page is contacted only during initial configuration to discover container inventory numbers. It is not contacted by normal background refreshes.

## Troubleshooting

### Municipality or address list is empty

- Confirm that the [Ecoservice schedules page](https://ecoservice.lt/grafikai/) opens in a browser.
- Restart the configuration flow and select an exact municipality suggestion.
- For address filtering, enter the beginning of the street/address, not text from the middle.

### No collection dates are found

- Confirm that each selected inventory number appears under the same VASA account and that its VASA calendar contains future dates.
- Reload the integration from **Settings → Devices & services**.
- Review Home Assistant logs for `ecoservice_waste_collection`.

### Calendar state is `off`

That state means no all-day collection event is active today. Open Home Assistant's Calendar panel to browse future events, or inspect the calendar entity's `upcoming_events` attribute.

### VASA sensors are unavailable or unknown

- Confirm the same credentials work at [VASA self-service](https://savitarna.vasa.lt/).
- Accounts that require a government-gateway login or additional two-factor verification are not supported.
- Verify that the selected inventory numbers exist in the VASA account and that VASA provides a successful (`Aptarnautas`) record with a weight.
- Temporary VASA failures retain cached values but mark the affected sensors unavailable until a successful refresh.

### Reporting a problem

Search existing [GitHub Issues](https://github.com/kubickasa/ecoservice_waste_collection/issues) and open a new issue if needed. Include the Home Assistant version, integration version, relevant redacted logs, and reproducible steps. Remove addresses, inventory numbers, credentials, access tokens, invoices, and other personal information before posting.

## Removal

1. Remove the integration entry from **Settings → Devices & services**.
2. Remove the integration in HACS, or manually delete `/config/custom_components/ecoservice_waste_collection`.
3. Restart Home Assistant.
4. If desired, remove any remaining dashboard cards or automations that referenced its entities.

## Privacy and disclaimer

- No telemetry is sent by this integration.
- Municipality, address, container identifiers, and VASA results are stored in the local Home Assistant instance.
- VASA credentials are stored in the Home Assistant config entry under `.storage`; they are not exposed as entity attributes or intentionally written to logs. Protect the Home Assistant filesystem and backups.
- Configuring the integration authorizes it to send the supplied credentials directly to VASA and retrieve data available to that account.
- Public Power BI and VASA endpoints are third-party services and may change without notice.
- Use the integration at your own risk. The maintainers are not responsible for missed collections, billing decisions, data loss, or service availability.

## License

This project is licensed under the [MIT License](LICENSE).
