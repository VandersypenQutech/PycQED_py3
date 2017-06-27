import numpy as np
import os
import re
import urllib.request
import time
import pycqed as pq

from pycqed.measurement import measurement_control
from pycqed.instrument_drivers.virtual_instruments.pyqx.qx_client import qx_client
from pycqed.measurement.detector_functions import QX_Hard_Detector

from pycqed.measurement import sweep_functions as swf

from tess.TessConnect import TessConnection

tc = TessConnection()
tc.connect("simulate")
defualt_simulate_options = {
    "num_avg": 10000,
    "iterations": 1
}


def simulate_qasm_file(file_url, options={}):
    # file_url="uploads/asset/file/65/f27d92be-8505-43dc-af7d-4c395c70aaf9.qasm"
    print("SIMULATE")
    file_path = _retrieve_file_from_url(file_url)

    # Connect to the qx simulator
    MC = measurement_control.MeasurementControl(
        'MC', live_plot_enabled=False, verbose=True)

    qxc = qx_client()
    qxc.connect()
    time.sleep(0.5)
    qxc.create_qubits(5)
    try:

        qx_sweep = swf.QX_Hard_Sweep(qxc, file_path)
        qx_detector = QX_Hard_Detector(qxc, [file_path], num_avg=10000)
        sweep_points = range(len(qx_detector.randomizations[0]))
        # qx_detector.prepare(sweep_points)
        # Start measurment
        MC.set_detector_function(qx_detector)
        MC.set_sweep_function(qx_sweep)
        MC.set_sweep_points(sweep_points)
        dat = MC.run("run QASM")
        return _MC_result_to_chart_dict(dat)
    except:
        raise

        return []
    finally:
        qxc.disconnect()
        MC.close()


# Private
# -------


def _get_qasm_sweep_points(file_path):
    counter = 0
    with open(file_path) as f:
        line = f.readline()
        while(line):
            if re.match(r'(^|\s+)(measure|RO)(\s+|$)', line):
                counter += 1
            line = f.readline()

    return range(counter)


def _retrieve_file_from_url(file_url):

    file_name = file_url.split("/")[-1]
    base_path = os.path.join(
        pq.__path__[0], 'measurement', 'demonstrator_helper',
        'qasm_files', file_name)
    file_path = base_path
    # download file from server
    urllib.request.urlretrieve(file_url, file_path)
    return file_path


def _MC_result_to_chart_dict(result):
    for i in result:
        if(isinstance(result[i], np.ndarray)):
            result[i] = result[i].tolist()
    return [{
        "data-type": "chart",
        "data": result
    }]
