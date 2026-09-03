"""Future phone and external-IMU source adapters.

TODO:
- translate platform/device data into the ingestion boundary without filtering it here;
- preserve sensor identity, sampling rate, timestamp domain, calibration metadata, and units;
- support future high-rate external IMUs without assuming a particular vendor or transport;
- keep mobile SDK and native implementation details out of the backend core.
"""
