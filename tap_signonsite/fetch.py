import singer
import singer.metrics as metrics
from singer import metadata
from singer.bookmarks import get_bookmark
from tap_signonsite.utility import get_all_pages, formatDate


def get_all_sites(schemas, state, mdata):
    extraction_time = singer.utils.now()
    users = []
    companies = []

    with metrics.record_counter("sites") as s_counter:
        with metrics.record_counter("attendances") as a_counter:
            for response in get_all_pages("sites", "/sites"):
                sites = response["data"]
                for site in sites:
                    # handle sites record
                    with singer.Transformer() as transformer:
                        rec = transformer.transform(
                            site, schemas["sites"], metadata=metadata.to_map(mdata)
                        )
                    singer.write_record("sites", rec, time_extracted=extraction_time)
                    s_counter.increment()

                    # sync attendances if that schema is present (only there if selected)
                    if schemas.get("attendances"):
                        site_id = site["id"]

                        for attendance in get_attendances(site_id, state):
                            attendance["site_id"] = site_id
                            with singer.Transformer() as transformer:
                                rec = transformer.transform(
                                    attendance,
                                    schemas["attendances"],
                                    metadata=metadata.to_map(mdata),
                                )
                            singer.write_record(
                                "attendances", rec, time_extracted=extraction_time,
                            )

                            a_counter.increment()

                            # Transform doesn't mutate original record so the data is still there
                            if schemas.get("users"):
                                users.append(attendance["user"])
                            if schemas.get("companies"):
                                companies.append(attendance["company"])

                # Update attendances bookmark at the end
                if schemas.get("attendances"):
                    singer.write_bookmark(
                        state, "attendances", "since", formatDate(extraction_time),
                    )

                # get unique users and write records
                if schemas.get("users"):
                    user_ids = set()
                    for user in users:
                        if user["id"] not in user_ids:
                            user_ids.add(user["id"])
                            with singer.Transformer() as transformer:
                                transformed = transformer.transform(
                                    user,
                                    schemas["users"],
                                    metadata=metadata.to_map(mdata),
                                )
                            singer.write_record(
                                "users", transformed, time_extracted=extraction_time,
                            )

                # get unique companies and write records
                if schemas.get("companies"):
                    company_ids = set()
                    for company in companies:
                        if company["id"] not in company_ids:
                            company_ids.add(company["id"])
                            with singer.Transformer() as transformer:
                                transformed = transformer.transform(
                                    company,
                                    schemas["companies"],
                                    metadata=metadata.to_map(mdata),
                                )
                            singer.write_record(
                                "companies",
                                transformed,
                                time_extracted=extraction_time,
                            )

    return state


def get_attendances(site_id, state):
    bookmark_value = get_bookmark(state, "attendances", "since")

    for page in get_all_pages(
        "attendances", "/sites/{}/attendances".format(site_id), bookmark_value
    ):
        rows = page["data"]
        for attendance in rows:
            yield attendance

    return state
