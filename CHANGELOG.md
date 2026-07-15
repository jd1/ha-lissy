# Changelog

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
