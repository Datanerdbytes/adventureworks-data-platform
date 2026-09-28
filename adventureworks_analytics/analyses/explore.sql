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

select distinct
    finishedgoodsflag
from `quantum-echo-data-eng-prod.raw_adventureworks.dimproduct` limit 5;