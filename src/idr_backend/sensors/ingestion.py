"""Future IMU and device-observation ingestion.

TODO:
- accept phone and external-IMU sources through one normalized boundary;
- preserve source timestamps and metadata without silently fabricating samples;
- surface source availability, permission, and sampling failures explicitly;
- defer concrete transport, file, and platform integrations to adapters.
"""
