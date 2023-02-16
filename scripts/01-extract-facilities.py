import json
import sqlite3
import typing
from itertools import groupby
from operator import itemgetter

import us

DATA_PATH = "viewer/public/data"

FACILITIES_QUERY = """
SELECT
    EPAFacilityID,
    FacilityName AS name,
    FacilityState AS state,
    FacilityCity AS city,
    TRIM(
        COALESCE(FacilityStr1, '') || ' • ' || COALESCE(FacilityStr2, ''),
        ' •'
    ) AS address,
    FacilityZipCode AS zip,
    FacilityCountyFIPS AS county_fips,
    FacilityLatDecDegs AS lat,
    FacilityLongDecDegs AS lng
FROM
    tblFacility
ORDER BY
    state,
    county_fips,
    LOWER(city),
    LOWER(name);
"""

SUBMISSIONS_QUERY = """
SELECT
    EPAFacilityID,
    ParentCompanyName AS company_1,
    Company2Name AS company_2,
    OperatorName AS operator,
    JSON_GROUP_ARRAY(
        JSON_OBJECT(
            'id', FacilityID,
            'date', SUBSTR(CompletionCheckDate, 1, 10)
        )
    ) AS submissions
FROM
    (SELECT *
        FROM TblS1Facilities
        ORDER BY
            EPAFacilityID,
            CompletionCheckDate DESC
    )
GROUP BY
    EPAFacilityID;
"""

with open("data/manual/counties.json") as f:
    COUNTIES = {x["fips"]: x["name"] for x in json.load(f)}

with open("data/manual/county-fips-fixes.json") as f:
    FIPS_FIXES = json.load(f)


def get_raw(db_path: str, query: str) -> list[dict[str, typing.Any]]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    res = con.cursor().execute(query)
    return list(map(dict, res))


def get_facilities() -> list[dict[str, typing.Any]]:
    facilities = get_raw("data/raw/RMPFac.sqlite", FACILITIES_QUERY)
    info_from_submissions = {
        x["EPAFacilityID"]: x
        for x in get_raw("data/raw/RMPData.sqlite", SUBMISSIONS_QUERY)
    }

    for fac in facilities:
        fac_id = fac["EPAFacilityID"]
        fix = FIPS_FIXES.get(fac_id)
        if fix:
            fac["county_fips"] = fix
        elif fac["county_fips"] is None:
            raise ValueError(fac)
        fac.update(info_from_submissions[fac_id])
        fac["submissions"] = json.loads(fac["submissions"])

    return facilities


def write_states(facilities: list[dict[str, typing.Any]]) -> None:
    counts = []
    key = itemgetter("state")
    for state, _state_facs in groupby(sorted(facilities, key=key), key):
        state_facs = list(_state_facs)

        name = us.states.lookup(state).name
        counts.append(dict(abbr=state, name=name, count=len(state_facs)))

        dest = f"{DATA_PATH}/facilities/by-state/{state}.json"
        with open(dest, "w") as f:
            county_key = itemgetter("county_fips")
            by_county = [
                dict(
                    fips=fips,
                    name=COUNTIES[fips],
                    facilities=[
                        {
                            k: fac[k]
                            for k in ["EPAFacilityID", "name", "city", "address"]
                        }
                        for fac in county_facs
                    ],
                )
                for fips, county_facs in groupby(
                    sorted(state_facs, key=county_key), county_key
                )
            ]
            json.dump(dict(abbr=state, name=name, counties=by_county), f, indent=2)

    with open(f"{DATA_PATH}/facilities/states.json", "w") as f:
        json.dump(counts, f, indent=2)


def write_facilities(facilities: list[dict[str, typing.Any]]) -> None:
    for fac in facilities:
        dest = f"{DATA_PATH}/facilities/detail/{fac['EPAFacilityID']}.json"
        with open(dest, "w") as f:
            json.dump(fac, f, indent=2)


def main() -> None:
    facilities = get_facilities()
    write_states(facilities)
    write_facilities(facilities)


if __name__ == "__main__":
    main()
