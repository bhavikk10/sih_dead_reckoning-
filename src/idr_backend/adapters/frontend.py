"""Boundary deliberately kept free of UI and transport code.

The implemented mobile JSON contract lives in :mod:`idr_backend.service.models`.
The service converts a committed ``NavigationEstimate`` into a map-ready WGS-84
estimate and owns one ``NavigationFusionPipeline`` per navigation session.
Mobile applications must send raw sensor-frame IMU and WGS-84 GNSS; neither
Flutter/React Native view models nor HTTP concerns belong in this adapter layer.
"""
