# Changelog

## [0.6.0](https://github.com/jd1/ha-lissy/compare/v0.5.3...v0.6.0) (2026-08-14)


### Features

* **ci:** add opencode workflow to convert ai-pr issues into prs ([493bf9b](https://github.com/jd1/ha-lissy/commit/493bf9bc81d022133f640856287891d0899a0321))


### Bug Fixes

* **ci:** avoid duplicate runs and use valid hetzner model format ([b5f7b5c](https://github.com/jd1/ha-lissy/commit/b5f7b5c70f1fa0902fa0c82bd756c998f6db7d97))
* **ci:** register hetzner as custom opencode provider ([c74b92f](https://github.com/jd1/ha-lissy/commit/c74b92f4ba22649f3696d36e7538947a6f807831))
* **ci:** Use different model prefix ([0d0ba0a](https://github.com/jd1/ha-lissy/commit/0d0ba0a78ec2b4eac8c8d24de1a517753ef9c8ac))
* **lissy:** chain config-entry migration and assert final version ([55590b5](https://github.com/jd1/ha-lissy/commit/55590b51aeb9da5671727e8639114980a59f320f))

## [0.5.3](https://github.com/jd1/ha-lissy/compare/v0.5.2...v0.5.3) (2026-08-09)


### Bug Fixes

* **ci:** zip lissy contents flat for HACS zip_release extraction ([1be8ddf](https://github.com/jd1/ha-lissy/commit/1be8ddf9dd4259f0f85e7bab5e4e6dd830159df0))

## [0.5.2](https://github.com/jd1/ha-lissy/compare/v0.5.1...v0.5.2) (2026-08-09)


### Bug Fixes

* **ci:** Remove lissy folder from zip release ([22a43dd](https://github.com/jd1/ha-lissy/commit/22a43ddd02169ac631fae053de5c8751d2032d9e))

## [0.5.1](https://github.com/jd1/ha-lissy/compare/v0.5.0...v0.5.1) (2026-08-09)


### Bug Fixes

* **ci:** Remove custom_component folder from zip release ([db5950d](https://github.com/jd1/ha-lissy/commit/db5950dfffa9d700bdb2a89e93586a2e2a0bca1d))

## [0.5.0](https://github.com/jd1/ha-lissy/compare/v0.4.0...v0.5.0) (2026-08-09)


### Features

* **config_flow:** reject base_url that doesn't end with lissy/lissy.ly ([babdb02](https://github.com/jd1/ha-lissy/commit/babdb0260dc32b69c1b33f33b8cb1aa1ae090a28))
* **lissy:** expose device targets and add service translations ([8ec63ea](https://github.com/jd1/ha-lissy/commit/8ec63ea49ca942bfda5e7f3c291152f3c591cd21))


### Bug Fixes

* **api:** add return type to _get_session ([4f2456d](https://github.com/jd1/ha-lissy/commit/4f2456d5e8b3e195e5ce75c8283e54f6398473ff))
* **api:** cache session token, dedupe media-type warnings, skip redundant refetch ([4f5ee71](https://github.com/jd1/ha-lissy/commit/4f5ee717f9ab1263bb570c133e769d8a9cab17ec))
* **config_flow:** mask password field in config flow ([0b837f5](https://github.com/jd1/ha-lissy/commit/0b837f5b824e5f1c36660e77df11d8d3bafd57b8))
* **config_flow:** reuse Home Assistant's client session during validation ([db0e10d](https://github.com/jd1/ha-lissy/commit/db0e10df08afb0be2c73c2db033a639c0757dbc0))
* **coordinator:** use LissyConfigEntry type alias in __init__ ([92f4f05](https://github.com/jd1/ha-lissy/commit/92f4f051930cef3636cad5758b50106c36308b6d))
* **lissy:** detect invalid-login frameset and tidy review findings ([9320478](https://github.com/jd1/ha-lissy/commit/9320478983f9720dd7254932ded40d0b7662e340))
* **lissy:** guard token-redaction debug logs with isEnabledFor ([8e3225d](https://github.com/jd1/ha-lissy/commit/8e3225d20dad9730be3ba5ce00bff612d2aa6908))
* **lissy:** guard unset runtime_data and empty renew target set ([907a62e](https://github.com/jd1/ha-lissy/commit/907a62e1c4bba38427dbe42a69485522b5fb74d0))
* **lissy:** introduce LissyNotFoundError for mednr-not-found case ([f6c0b0e](https://github.com/jd1/ha-lissy/commit/f6c0b0e6aa702219d209800d0a272996d07c3bd6))
* **lissy:** move renew device target to a service field ([a3b5217](https://github.com/jd1/ha-lissy/commit/a3b52170ff508afb32b7fa526fd418f58c4707e3))
* **lissy:** require base_url and migrate legacy config entries ([e52074b](https://github.com/jd1/ha-lissy/commit/e52074bc28863d59e2966baab5c8e412e2fa6d7a))
* **sensor:** track current item state in LissyItemSensor ([0bd91e9](https://github.com/jd1/ha-lissy/commit/0bd91e925e90670ab62399fb21c0e48348d40521))
* **sensor:** use Home Assistant's configured timezone for days_until_due ([4b24cb9](https://github.com/jd1/ha-lissy/commit/4b24cb9dca308cd38b1ea3531571f3d0ce09da5c))


### Performance Improvements

* **lissy:** cache derived events and earliest due on coordinator update ([0695e6f](https://github.com/jd1/ha-lissy/commit/0695e6ff10c25aa18f5c3e87b328a4f2049d4219))


### Reverts

* **lissy:** drop session-token caching introduced for review finding [#11](https://github.com/jd1/ha-lissy/issues/11) ([90746d1](https://github.com/jd1/ha-lissy/commit/90746d16b6b0182549d4134a31f7826a2b6940da))

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
