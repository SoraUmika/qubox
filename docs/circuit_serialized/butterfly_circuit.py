
# Single QUA script generated at 2026-04-03 20:16:13.114762
# QUA library version: 1.2.6


from qm import CompilerOptionArguments
from qm.qua import *

with program() as prog:
    v1 = declare(fixed, )
    v2 = declare(fixed, )
    v3 = declare(fixed, )
    v4 = declare(fixed, )
    v5 = declare(fixed, )
    v6 = declare(fixed, )
    v7 = declare(bool, )
    v8 = declare(bool, )
    v9 = declare(bool, )
    v10 = declare(int, )
    v11 = declare(int, )
    v12 = declare(bool, )
    with for_(v10,0,(v10<2048),(v10+1)):
        assign(v11, 0)
        assign(v12, False)
        with while_(((v12^True)&(v11<8))):
            measure("readout", "resonator", dual_demod.full("cos", "sin", v1), dual_demod.full("minus_sin", "cos", v2))
            align()
            measure("readout", "resonator", dual_demod.full("cos", "sin", v3), dual_demod.full("minus_sin", "cos", v4))
            align()
            measure("readout", "resonator", dual_demod.full("cos", "sin", v5), dual_demod.full("minus_sin", "cos", v6))
            align()
            assign(v12, (v1<0.0))
            with if_((v12^True)):
                play("x180", "transmon", condition=(v1>0.0))
                align()
            assign(v11, (v11+1))
        r1 = declare_stream()
        save(v7, r1)
        save(v8, r1)
        save(v9, r1)
        r2 = declare_stream()
        save(v1, r2)
        r3 = declare_stream()
        save(v2, r3)
        r4 = declare_stream()
        save(v3, r4)
        r5 = declare_stream()
        save(v4, r5)
        r6 = declare_stream()
        save(v5, r6)
        r7 = declare_stream()
        save(v6, r7)
        r8 = declare_stream()
        save(v12, r8)
        r9 = declare_stream()
        save(v11, r9)
        assign(v11, 0)
        assign(v12, False)
        play("x180", "transmon")
        align()
        with while_(((v12^True)&(v11<8))):
            measure("readout", "resonator", dual_demod.full("cos", "sin", v1), dual_demod.full("minus_sin", "cos", v2))
            align()
            measure("readout", "resonator", dual_demod.full("cos", "sin", v3), dual_demod.full("minus_sin", "cos", v4))
            align()
            measure("readout", "resonator", dual_demod.full("cos", "sin", v5), dual_demod.full("minus_sin", "cos", v6))
            align()
            assign(v12, (v1>0.0))
            with if_((v12^True)):
                play("x180", "transmon", condition=(v1<0.0))
                align()
            assign(v11, (v11+1))
        save(v7, r1)
        save(v8, r1)
        save(v9, r1)
        save(v1, r2)
        save(v2, r3)
        save(v3, r4)
        save(v4, r5)
        save(v5, r6)
        save(v6, r7)
        save(v12, r8)
        save(v11, r9)
        r10 = declare_stream()
        save(v10, r10)
        wait(10000, )
    with stream_processing():
        r1.map(FUNCTIONS.boolean_to_int()).buffer(3).buffer(2).buffer(2048).save("states")
        r2.buffer(2).buffer(2048).save("I0")
        r3.buffer(2).buffer(2048).save("Q0")
        r4.buffer(2).buffer(2048).save("I1")
        r5.buffer(2).buffer(2048).save("Q1")
        r6.buffer(2).buffer(2048).save("I2")
        r7.buffer(2).buffer(2048).save("Q2")
        r8.map(FUNCTIONS.boolean_to_int()).buffer(2).average().save("acceptance_rate")
        r9.buffer(2).average().save("average_tries")
        r10.save("iteration")

config = {
    "version": 1,
    "controllers": {
        "con1": {
            "analog_outputs": {
                "1": {
                    "offset": 0.0,
                },
                "2": {
                    "offset": 0.0,
                },
                "3": {
                    "offset": 0.0,
                },
                "4": {
                    "offset": 0.0,
                },
                "5": {
                    "offset": 0.0,
                },
                "6": {
                    "offset": 0.0,
                },
                "7": {
                    "offset": 0.0,
                },
                "8": {
                    "offset": 0.0,
                },
                "9": {
                    "offset": 0.0,
                },
                "10": {
                    "offset": 0.0,
                },
            },
            "digital_outputs": {
                "1": {},
                "2": {},
                "3": {},
                "5": {},
            },
            "analog_inputs": {
                "1": {
                    "offset": 0.00947713,
                },
                "2": {
                    "offset": 0.00962465,
                },
            },
        },
    },
    "octaves": {
        "oct1": {
            "RF_outputs": {
                "1": {
                    "LO_frequency": 8800000000.0,
                    "LO_source": "internal",
                    "output_mode": "always_on",
                    "gain": -10.0,
                },
                "3": {
                    "LO_frequency": 6200000000.0,
                    "LO_source": "internal",
                    "output_mode": "always_on",
                    "gain": 3.0,
                },
                "5": {
                    "LO_frequency": 5400000000.0,
                    "LO_source": "internal",
                    "output_mode": "always_on",
                    "gain": 0.0,
                },
                "4": {
                    "LO_frequency": 7000000000.0,
                    "LO_source": "external",
                    "output_mode": "always_on",
                    "gain": 6.5,
                },
                "2": {
                    "LO_frequency": 3500000000.0,
                    "LO_source": "external",
                    "output_mode": "always_on",
                    "gain": 7.5,
                },
            },
            "RF_inputs": {
                "1": {
                    "RF_source": "RF_in",
                    "LO_frequency": 8800000000.0,
                    "LO_source": "internal",
                    "IF_mode_I": "direct",
                    "IF_mode_Q": "direct",
                },
            },
            "connectivity": "con1",
        },
    },
    "elements": {
        "resonator": {
            "RF_inputs": {
                "port": ['oct1', 1],
            },
            "intermediate_frequency": -50000000.0,
            "operations": {
                "const": "const_pulse",
                "zero": "zero_pulse",
                "readout": "readout_pulse",
            },
            "RF_outputs": {
                "port": ['oct1', 1],
            },
            "time_of_flight": 280,
            "digitalInputs": {
                "switch": {
                    "port": ['con1', 1],
                    "delay": 0,
                    "buffer": 0,
                },
                "pump": {
                    "port": ['con1', 2],
                    "delay": 114,
                    "buffer": 18,
                },
            },
        },
        "transmon": {
            "RF_inputs": {
                "port": ['oct1', 3],
            },
            "intermediate_frequency": -50000000.0,
            "operations": {
                "const": "const_pulse",
                "zero": "zero_pulse",
                "readout": "readout_pulse",
                "ref_r180": "ref_r180_pulse",
                "r0": "r0_pulse",
                "x180": "x180_pulse",
                "x90": "x90_pulse",
                "xn90": "xn90_pulse",
                "y180": "y180_pulse",
                "y90": "y90_pulse",
                "yn90": "yn90_pulse",
            },
            "digitalInputs": {
                "switch": {
                    "port": ['con1', 3],
                    "delay": 57,
                    "buffer": 18,
                },
            },
        },
        "storage": {
            "RF_inputs": {
                "port": ['oct1', 5],
            },
            "intermediate_frequency": -50000000.0,
            "operations": {
                "const": "const_pulse",
                "zero": "zero_pulse",
                "readout": "readout_pulse",
            },
            "digitalInputs": {
                "switch": {
                    "port": ['con1', 5],
                    "delay": 57,
                    "buffer": 18,
                },
            },
        },
        "storage_gf": {
            "RF_inputs": {
                "port": ['oct1', 4],
            },
            "intermediate_frequency": -50000000.0,
            "operations": {
                "const": "const_pulse",
                "zero": "zero_pulse",
                "readout": "readout_pulse",
            },
            "digitalInputs": {
                "switch": {
                    "port": ['con1', 2],
                    "delay": 57,
                    "buffer": 18,
                },
            },
        },
        "resonator_gf": {
            "RF_inputs": {
                "port": ['oct1', 2],
            },
            "intermediate_frequency": -50000000.0,
            "operations": {
                "const": "const_pulse",
                "zero": "zero_pulse",
                "readout": "readout_pulse",
            },
            "digitalInputs": {
                "switch": {
                    "port": ['con1', 2],
                    "delay": 57,
                    "buffer": 18,
                },
            },
        },
    },
    "mixers": {},
    "pulses": {
        "const_pulse": {
            "operation": "control",
            "length": 1000,
            "waveforms": {
                "I": "const_wf",
                "Q": "zero_wf",
            },
            "digital_marker": "ON",
        },
        "zero_pulse": {
            "operation": "control",
            "length": 1000,
            "waveforms": {
                "I": "zero_wf",
                "Q": "zero_wf",
            },
            "digital_marker": "ON",
        },
        "readout_pulse": {
            "operation": "measurement",
            "length": 400,
            "waveforms": {
                "I": "readout_I_wf",
                "Q": "readout_Q_wf",
            },
            "digital_marker": "ON",
            "integration_weights": {
                "cos": "readout_cosine_weights",
                "sin": "readout_sine_weights",
                "minus_sin": "readout_minus_weights",
            },
        },
        "transmon_ref_r180_pulse": {
            "operation": "control",
            "length": 16,
            "waveforms": {
                "I": "transmon_ref_r180_I",
                "Q": "transmon_ref_r180_Q",
            },
            "digital_marker": "ON",
        },
        "transmon_ref_r180_pulse_1": {
            "operation": "control",
            "length": 16,
            "waveforms": {
                "I": "transmon_ref_r180_I_1",
                "Q": "transmon_ref_r180_Q_1",
            },
            "digital_marker": "ON",
        },
        "r0_pulse": {
            "operation": "control",
            "length": 16,
            "waveforms": {
                "I": "r0_I_wf",
                "Q": "r0_Q_wf",
            },
            "digital_marker": "ON",
        },
        "ref_r180_pulse": {
            "operation": "control",
            "length": 16,
            "waveforms": {
                "I": "ref_r180_I_wf",
                "Q": "ref_r180_Q_wf",
            },
            "digital_marker": "ON",
        },
        "x180_pulse": {
            "operation": "control",
            "length": 16,
            "waveforms": {
                "I": "x180_I_wf",
                "Q": "x180_Q_wf",
            },
            "digital_marker": "ON",
        },
        "x90_pulse": {
            "operation": "control",
            "length": 16,
            "waveforms": {
                "I": "x90_I_wf",
                "Q": "x90_Q_wf",
            },
            "digital_marker": "ON",
        },
        "xn90_pulse": {
            "operation": "control",
            "length": 16,
            "waveforms": {
                "I": "xn90_I_wf",
                "Q": "xn90_Q_wf",
            },
            "digital_marker": "ON",
        },
        "y180_pulse": {
            "operation": "control",
            "length": 16,
            "waveforms": {
                "I": "y180_I_wf",
                "Q": "y180_Q_wf",
            },
            "digital_marker": "ON",
        },
        "y90_pulse": {
            "operation": "control",
            "length": 16,
            "waveforms": {
                "I": "y90_I_wf",
                "Q": "y90_Q_wf",
            },
            "digital_marker": "ON",
        },
        "yn90_pulse": {
            "operation": "control",
            "length": 16,
            "waveforms": {
                "I": "yn90_I_wf",
                "Q": "yn90_Q_wf",
            },
            "digital_marker": "ON",
        },
    },
    "digital_waveforms": {
        "ON": {
            "samples": [[1, 0]],
        },
        "OFF": {
            "samples": [[0, 0]],
        },
    },
    "waveforms": {
        "zero_wf": {
            "type": "constant",
            "sample": 0.0,
        },
        "const_wf": {
            "type": "constant",
            "sample": 0.24,
        },
        "readout_I_wf": {
            "type": "arbitrary",
            "samples": [0.04] * 256 + [0.0] * 144,
        },
        "readout_Q_wf": {
            "type": "arbitrary",
            "samples": [0.0] * 400,
        },
        "transmon_ref_r180_I": {
            "type": "arbitrary",
            "samples": [0.0, 0.0032110078533528616, 0.010004275656551818, 0.022163330243511945, 0.04034432713860597, 0.06252315529880662, 0.08345191895080185] + [0.09634182971207712] * 2 + [0.08345191895080185, 0.06252315529880662, 0.04034432713860597, 0.022163330243511945, 0.010004275656551818, 0.0032110078533528616, 0.0],
        },
        "transmon_ref_r180_Q": {
            "type": "arbitrary",
            "samples": [0.0] * 16,
        },
        "transmon_ref_r180_I_1": {
            "type": "arbitrary",
            "samples": [0.0, 0.002750303925511976, 0.0085688979494049, 0.018983414851352808, 0.034555867306766734, 0.053552556489124895, 0.07147853595008807] + [0.08251904839518133] * 2 + [0.07147853595008807, 0.053552556489124895, 0.034555867306766734, 0.018983414851352808, 0.0085688979494049, 0.002750303925511976, 0.0],
        },
        "transmon_ref_r180_Q_1": {
            "type": "arbitrary",
            "samples": [0.0] * 16,
        },
        "r0_I_wf": {
            "type": "arbitrary",
            "samples": [0.0] * 16,
        },
        "r0_Q_wf": {
            "type": "arbitrary",
            "samples": [0.0] * 16,
        },
        "ref_r180_I_wf": {
            "type": "arbitrary",
            "samples": [0.0, 0.002750303925511976, 0.0085688979494049, 0.018983414851352808, 0.034555867306766734, 0.053552556489124895, 0.07147853595008807] + [0.08251904839518133] * 2 + [0.07147853595008807, 0.053552556489124895, 0.034555867306766734, 0.018983414851352808, 0.0085688979494049, 0.002750303925511976, 0.0],
        },
        "ref_r180_Q_wf": {
            "type": "arbitrary",
            "samples": [0.0] * 16,
        },
        "x180_I_wf": {
            "type": "arbitrary",
            "samples": [0.0, 0.002750303925511976, 0.0085688979494049, 0.018983414851352808, 0.034555867306766734, 0.053552556489124895, 0.07147853595008807] + [0.08251904839518133] * 2 + [0.07147853595008807, 0.053552556489124895, 0.034555867306766734, 0.018983414851352808, 0.0085688979494049, 0.002750303925511976, 0.0],
        },
        "x180_Q_wf": {
            "type": "arbitrary",
            "samples": [0.0] * 16,
        },
        "x90_I_wf": {
            "type": "arbitrary",
            "samples": [0.0, 0.001375151962755988, 0.00428444897470245, 0.009491707425676404, 0.017277933653383367, 0.026776278244562447, 0.03573926797504404] + [0.041259524197590665] * 2 + [0.03573926797504404, 0.026776278244562447, 0.017277933653383367, 0.009491707425676404, 0.00428444897470245, 0.001375151962755988, 0.0],
        },
        "x90_Q_wf": {
            "type": "arbitrary",
            "samples": [0.0] * 16,
        },
        "xn90_I_wf": {
            "type": "arbitrary",
            "samples": [0.0, -0.001375151962755988, -0.00428444897470245, -0.009491707425676404, -0.017277933653383367, -0.026776278244562447, -0.03573926797504404] + [-0.041259524197590665] * 2 + [-0.03573926797504404, -0.026776278244562447, -0.017277933653383367, -0.009491707425676404, -0.00428444897470245, -0.001375151962755988, 0.0],
        },
        "xn90_Q_wf": {
            "type": "arbitrary",
            "samples": [0.0] * 16,
        },
        "y180_I_wf": {
            "type": "arbitrary",
            "samples": [0.0, 1.684075449530321e-19, 5.246936722979515e-19, 1.1623989117297773e-18, 2.1159366144496276e-18, 3.279148344528231e-18, 4.3767980129507186e-18] + [5.052834424292218e-18] * 2 + [4.3767980129507186e-18, 3.279148344528231e-18, 2.1159366144496276e-18, 1.1623989117297773e-18, 5.246936722979515e-19, 1.684075449530321e-19, 0.0],
        },
        "y180_Q_wf": {
            "type": "arbitrary",
            "samples": [0.0, -0.002750303925511976, -0.0085688979494049, -0.018983414851352808, -0.034555867306766734, -0.053552556489124895, -0.07147853595008807] + [-0.08251904839518133] * 2 + [-0.07147853595008807, -0.053552556489124895, -0.034555867306766734, -0.018983414851352808, -0.0085688979494049, -0.002750303925511976, 0.0],
        },
        "y90_I_wf": {
            "type": "arbitrary",
            "samples": [0.0, 8.420377247651605e-20, 2.6234683614897576e-19, 5.811994558648886e-19, 1.0579683072248138e-18, 1.6395741722641155e-18, 2.1883990064753593e-18] + [2.526417212146109e-18] * 2 + [2.1883990064753593e-18, 1.6395741722641155e-18, 1.0579683072248138e-18, 5.811994558648886e-19, 2.6234683614897576e-19, 8.420377247651605e-20, 0.0],
        },
        "y90_Q_wf": {
            "type": "arbitrary",
            "samples": [0.0, -0.001375151962755988, -0.00428444897470245, -0.009491707425676404, -0.017277933653383367, -0.026776278244562447, -0.03573926797504404] + [-0.041259524197590665] * 2 + [-0.03573926797504404, -0.026776278244562447, -0.017277933653383367, -0.009491707425676404, -0.00428444897470245, -0.001375151962755988, 0.0],
        },
        "yn90_I_wf": {
            "type": "arbitrary",
            "samples": [0.0, -8.420377247651605e-20, -2.6234683614897576e-19, -5.811994558648886e-19, -1.0579683072248138e-18, -1.6395741722641155e-18, -2.1883990064753593e-18] + [-2.526417212146109e-18] * 2 + [-2.1883990064753593e-18, -1.6395741722641155e-18, -1.0579683072248138e-18, -5.811994558648886e-19, -2.6234683614897576e-19, -8.420377247651605e-20, 0.0],
        },
        "yn90_Q_wf": {
            "type": "arbitrary",
            "samples": [0.0, 0.001375151962755988, 0.00428444897470245, 0.009491707425676404, 0.017277933653383367, 0.026776278244562447, 0.03573926797504404] + [0.041259524197590665] * 2 + [0.03573926797504404, 0.026776278244562447, 0.017277933653383367, 0.009491707425676404, 0.00428444897470245, 0.001375151962755988, 0.0],
        },
    },
    "oscillators": {},
    "integration_weights": {
        "readout_cosine_weights": {
            "cosine": [[1.0, 400]],
            "sine": [[0.0, 400]],
        },
        "readout_sine_weights": {
            "cosine": [[0.0, 400]],
            "sine": [[1.0, 400]],
        },
        "readout_minus_weights": {
            "cosine": [[0.0, 400]],
            "sine": [[-1.0, 400]],
        },
    },
}

loaded_config = None

