/* @datacloud.settings
{
  "version": 1,
  "service": "BIG_QUERY",
  "connectionInfo": {
    "billingProjectId": "INHERIT"
  },
  "dialect": "GOOGLE_SQL"
}
*/

SELECT  *
FROM `quantum-echo-data-eng-prod.raw_adventureworks.dimcustomer` limit 5;

