# Changelog

## [0.4.0](https://github.com/jd1/ha-lissy/compare/v0.3.0...v0.4.0) (2026-07-20)


### Features

* **sensor:** add device_class=DATE to date-returning sensors ([d2e9732](https://github.com/jd1/ha-lissy/commit/d2e9732609cd44d80622d694e6f4ab469b23580e))


### Bug Fixes

* **config_flow:** strip username, drop username from reauth, URL selector for base_url ([d27901c](https://github.com/jd1/ha-lissy/commit/d27901c5969211c38be0f787780ed59112728135))
* **coordinator:** pass config_entry to DataUpdateCoordinator; trigger reauth on auth failure in renew ([13f4f1a](https://github.com/jd1/ha-lissy/commit/13f4f1a8a9656debf735d35097dda01be356362a))
* **dev:** include automations.yaml in configuration.yaml stub ([7625131](https://github.com/jd1/ha-lissy/commit/76251315fc89f7ce227b233aa76494f12c63b21c))
* **lissy:** add CONFIG_SCHEMA required by hassfest ([eec8148](https://github.com/jd1/ha-lissy/commit/eec8148d32b62c5fa6f682acc6239581d1124676))
* **lissy:** remove unsupported device filter from renew service target ([b8ce95a](https://github.com/jd1/ha-lissy/commit/b8ce95a8821bb0e8f02650ab4cc902ce31ad4252))
* remove duplicate DeviceInfo registration from __init__.py ([af51e53](https://github.com/jd1/ha-lissy/commit/af51e53a67010250ff38bb8d300430f0f69a87ce))
* **scraper:** urljoin for host derivation, header-anchored table selection, redact session tokens from debug logs ([83dad18](https://github.com/jd1/ha-lissy/commit/83dad186c007cecf4d25f83fb27575f6a7a36d1a))

## [0.3.0](https://github.com/jd1/ha-lissy/compare/v0.2.0...v0.3.0) (2026-07-15)


### Features

* add auto-renew blueprint ([cb41ee0](https://github.com/jd1/ha-lissy/commit/cb41ee0234effc2feddbe595c8aa8fadce530d29))
* add device targeting for renew service, fix summary sensor validation, bump to 0.2.0 ([9cd612f](https://github.com/jd1/ha-lissy/commit/9cd612f8d670e246d2b39c07298f6ae24227abe1))
* remove returned-book entities from registry ([acce2f6](https://github.com/jd1/ha-lissy/commit/acce2f6add01411a95f48d1502cbb936ff4281fa))
* **renew:** replace mednr field with entity targeting ([a97635e](https://github.com/jd1/ha-lissy/commit/a97635e840acc99034b558a5b99a0c1bd532092a))
* **sensor:** expose days_until_due attribute ([5207f02](https://github.com/jd1/ha-lissy/commit/5207f0266c20d658a87a5a45112232457298297d))


### Bug Fixes

* add RenewResponse TypedDict, fix RenewResult.due_date, type coordinator, guard empty device_id ([8ab3e0a](https://github.com/jd1/ha-lissy/commit/8ab3e0ad0fa6c83118b04e870a1c87a1a689912e))
* **api:** report tableless renewal response as failure ([755d01c](https://github.com/jd1/ha-lissy/commit/755d01cfceee5ba1ee05d734f4ce5ca62331f6c6))
* **api:** wrap network calls in typed errors; add tests and HACS zip release ([aab3d24](https://github.com/jd1/ha-lissy/commit/aab3d248ba40ff5603d742fcc971be2c742fbf57))
* **ci:** use release-please manifest mode so version bumps from 0.2.0 ([885e77d](https://github.com/jd1/ha-lissy/commit/885e77d372e7e61b64a356881963ce8d4c14a3b9))
* register renew service in async_setup, fix ServiceCall target handling ([99fc181](https://github.com/jd1/ha-lissy/commit/99fc1810db3de18468d650b309333a7a98957aa7))
* sort manifest keys, remove invalid entity_category, add brand icon ([85f9067](https://github.com/jd1/ha-lissy/commit/85f90671843382d828ce2d3ca483470694abc129))
* surface renewal failures as HomeAssistantError, convert verlaengert to bool ([833ca1a](https://github.com/jd1/ha-lissy/commit/833ca1a46dcdcffdc0d816678d88d453f54f9f3b))
