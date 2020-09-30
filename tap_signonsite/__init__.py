import os
import json
import singer
from singer import metadata

from tap_signonsite.utility import get_abs_path, session
from tap_signonsite.config import SYNC_FUNCTIONS, SUB_STREAMS

logger = singer.get_logger()

REQUIRED_CONFIG_KEYS = ["api_key"]


def load_schemas():
    schemas = {}

    for filename in os.listdir(get_abs_path("schemas")):
        path = get_abs_path("schemas") + "/" + filename
        file_raw = filename.replace(".json", "")
        with open(path) as file:
            schemas[file_raw] = json.load(file)

    return schemas


def populate_metadata(schema_name, schema):
    mdata = metadata.new()
    mdata = metadata.write(mdata, (), "table-key-properties", ["id"])

    for field_name in schema["properties"].keys():
        mdata = metadata.write(
            mdata,
            ("properties", field_name),
            "inclusion",
            "automatic" if field_name == "id" else "available",
        )

    return mdata


def get_catalog():
    raw_schemas = load_schemas()
    streams = []

    for schema_name, schema in raw_schemas.items():

        # get metadata for each field
        mdata = populate_metadata(schema_name, schema)

        # create and add catalog entry
        catalog_entry = {
            "stream": schema_name,
            "tap_stream_id": schema_name,
            "schema": schema,
            "metadata": metadata.to_list(mdata),
            "key_properties": ["id"],
        }
        streams.append(catalog_entry)

    return {"streams": streams}


def do_discover():
    catalog = get_catalog()
    # dump catalog
    print(json.dumps(catalog, indent=2))


def get_selected_streams(catalog):
    """
    Gets selected streams.  Checks schema's 'selected'
    first -- and then checks metadata, looking for an empty
    breadcrumb and mdata with a 'selected' entry
    """
    selected_streams = []
    for stream in catalog["streams"]:
        stream_metadata = stream["metadata"]
        if stream["schema"].get("selected", False):
            selected_streams.append(stream["tap_stream_id"])
        else:
            for entry in stream_metadata:
                # stream metadata will have empty breadcrumb
                if not entry["breadcrumb"] and entry["metadata"].get("selected", None):
                    selected_streams.append(stream["tap_stream_id"])

    return selected_streams


def get_stream_from_catalog(stream_id, catalog):
    for stream in catalog["streams"]:
        if stream["tap_stream_id"] == stream_id:
            return stream
    return None


def do_sync(config, state, catalog):
    session.headers.update({"Authorization": "Bearer " + config["api_key"]})

    selected_stream_ids = get_selected_streams(catalog)

    for stream in catalog["streams"]:
        stream_id = stream["tap_stream_id"]
        stream_schema = stream["schema"]
        mdata = stream["metadata"]

        # if it is a "sub_stream", it will be sync'd by its parent
        if not SYNC_FUNCTIONS.get(stream_id):
            continue

        # if stream is selected, write schema and sync
        if stream_id in selected_stream_ids:
            singer.write_schema(stream_id, stream_schema, stream["key_properties"])

            # get sync function and any sub streams
            sync_func = SYNC_FUNCTIONS[stream_id]
            sub_stream_ids = SUB_STREAMS.get(stream_id, None)

            # sync stream
            if not sub_stream_ids:
                state = sync_func(stream_schema, state, mdata)

            # handle streams with sub streams
            else:
                stream_schemas = {stream_id: stream_schema}

                # get and write selected sub stream schemas
                for sub_stream_id in sub_stream_ids:
                    if sub_stream_id in selected_stream_ids:
                        sub_stream = get_stream_from_catalog(sub_stream_id, catalog)
                        stream_schemas[sub_stream_id] = sub_stream["schema"]
                        singer.write_schema(
                            sub_stream_id,
                            sub_stream["schema"],
                            sub_stream["key_properties"],
                        )

                # sync stream and it's sub streams
                state = sync_func(stream_schemas, state, mdata)

            singer.write_state(state)


@singer.utils.handle_top_exception(logger)
def main():
    args = singer.utils.parse_args(REQUIRED_CONFIG_KEYS)

    if args.discover:
        do_discover()
    else:
        catalog = args.properties if args.properties else get_catalog()
        do_sync(args.config, args.state, catalog)


if __name__ == "__main__":
    main()
