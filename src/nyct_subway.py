"""MTA's proto2 extensions used by the subway estimator.

Field names/numbers follow the MTA-linked gtfs-realtime-NYCT.proto:
https://www.mta.info/developers (NYC Subway protobuf link).
Register descriptors against the official GTFS bindings, without a protoc runtime.
"""
from google.protobuf import descriptor_pb2, descriptor_pool
from google.transit import gtfs_realtime_pb2 as gtfs

schema = descriptor_pb2.FileDescriptorProto(
    name="deskmate-nyct.proto", package="transit_realtime", syntax="proto2",
    dependency=[gtfs.DESCRIPTOR.name])


def message(name, fields):
    msg = schema.message_type.add(name=name)
    for name, number, kind, repeated, type_name in fields:
        field = msg.field.add(name=name, number=number, type=kind,
                              label=3 if repeated else 1)
        if type_name:
            field.type_name = ".transit_realtime." + type_name


# FieldDescriptorProto types: string=9, message=11, bool=8, int32=5.
message("TripReplacementPeriod", [("route_id", 1, 9, False, None),
                                 ("replacement_period", 2, 11, False, "TimeRange")])
message("NyctFeedHeader", [("nyct_subway_version", 1, 9, False, None),
                           ("trip_replacement_period", 2, 11, True, "TripReplacementPeriod")])
message("NyctTripDescriptor", [("train_id", 1, 9, False, None),
                               ("is_assigned", 2, 8, False, None),
                               ("direction", 3, 5, False, None)])
message("NyctStopTimeUpdate", [("scheduled_track", 1, 9, False, None),
                              ("actual_track", 2, 9, False, None)])
for name, target, kind in [("nyct_feed_header", "FeedHeader", "NyctFeedHeader"),
                           ("nyct_trip_descriptor", "TripDescriptor", "NyctTripDescriptor"),
                           ("nyct_stop_time_update", "TripUpdate.StopTimeUpdate", "NyctStopTimeUpdate")]:
    schema.extension.add(name=name, number=1001, label=1, type=11,
                         extendee=".transit_realtime." + target,
                         type_name=".transit_realtime." + kind)

DESCRIPTOR = descriptor_pool.Default().AddSerializedFile(schema.SerializeToString())
nyct_feed_header = DESCRIPTOR.extensions_by_name["nyct_feed_header"]
nyct_trip_descriptor = DESCRIPTOR.extensions_by_name["nyct_trip_descriptor"]
nyct_stop_time_update = DESCRIPTOR.extensions_by_name["nyct_stop_time_update"]
