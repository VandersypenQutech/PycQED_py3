# This is a virtual instrument abstracting a homodyne
# source which controls RF and LO sources

import logging
import numpy as np
from time import time
from qcodes.instrument.base import Instrument
from qcodes.utils import validators as vals
from qcodes.instrument.parameter import ManualParameter
# Used for uploading the right AWG sequences
from pycqed.measurement.pulse_sequences import standard_sequences as st_seqs
import time


class HeterodyneInstrument(Instrument):

    '''
    This is a virtual instrument for a homodyne source

    Instrument is CBox, UHFQC and ATS compatible

    Todo:
        - Add power settings
        - Add integration time settings
        - Build test suite
        - Add parameter Heterodyne voltage (that returns a complex value/ 2 values)
        - Add different demodulation settings.
        - Add fading plots that shows the last measured avg transients
          and points in the IQ-plane in the second window
        - Add option to use CBox integration averaging mode and verify
           identical results
    '''
    shared_kwargs = ['RF', 'LO', 'AWG']

    def __init__(self, name,  RF, LO, AWG=None, acquisition_instr=None, acquisition_instr_controller=None,
                 single_sideband_demod=False, **kw):
        logging.info(__name__ + ' : Initializing instrument')
        Instrument.__init__(self, name, **kw)

        self.LO = LO
        self.RF = RF
        self.AWG = AWG
        self.add_parameter('frequency',
                           label='Heterodyne frequency',
                           unit='Hz',
                           get_cmd=self.do_get_frequency,
                           set_cmd=self.do_set_frequency,
                           vals=vals.Numbers(9e3, 40e9))
        self.add_parameter('f_RO_mod', parameter_class=ManualParameter,
                           vals=vals.Numbers(-600e6, 600e6),
                           label='Intermodulation frequency',
                           unit='Hz', initial_value=10e6)
        self.add_parameter('RF_power', label='RF power',
                           unit='dBm',
                           set_cmd=self.do_set_RF_power,
                           get_cmd=self.do_get_RF_power)
        self.add_parameter('single_sideband_demod',
                           label='Single sideband demodulation',
                           parameter_class=ManualParameter)
        self.add_parameter('acquisition_instr',
                           set_cmd=self._do_set_acquisition_instr,
                           get_cmd=self._do_get_acquisition_instr,
                           vals=vals.Anything())
        self.add_parameter('acquisition_instr_controller',
                           set_cmd=self._do_set_acquisition_instr_controller,
                           get_cmd=self._do_get_acquisition_instr_controller,
                           vals=vals.Anything())
        self.add_parameter('nr_averages',
                           parameter_class=ManualParameter,
                           initial_value=1024,
                           vals=vals.Numbers(min_value=0, max_value=int(1e6)))

        self.set('single_sideband_demod', single_sideband_demod)
        self._awg_seq_filename = 'Heterodyne_marker_seq_RF_mod'
        self._disable_auto_seq_loading = True
        self.acquisition_instr(acquisition_instr)
        self.acquisition_instr_controller(acquisition_instr_controller)

    def set_sources(self, status):
        self.RF.set('status', status)
        self.LO.set('status', status)

    def do_set_frequency(self, val):
        self._frequency = val
        # this is the definition agreed upon in issue 131
        self.RF.set('frequency', val)
        self.LO.set('frequency', val-self.f_RO_mod.get())

    def do_get_frequency(self):
        freq = self.RF.frequency()
        LO_freq = self.LO.frequency()
        if LO_freq != freq-self.f_RO_mod():
            logging.warning('f_RO_mod between RF and LO is not set correctly')
        return freq

    def do_set_RF_power(self, val):
        self.RF.power(val)
        self._RF_power = val
        # internally stored to allow setting RF from stored setting

    def do_get_RF_power(self):
        return self._RF_power

    def do_set_status(self, val):
        self.state = val
        if val == 'On':
            self.LO.on()
            self.RF.on()
        else:
            self.LO.off()
            self.RF.off()

    def do_get_status(self):
        if (self.LO.get('status').startswith('On')and
                self.RF.get('status').startswith('On')):
            return 'On'
        elif (self.LO.get('status').startswith('Off') and
                self.RF.get('status').startswith('Off')):
            return 'Off'
        else:
            return 'LO: %s, RF: %s' % (self.LO.get('status'),
                                       self.RF.get('status'))

    def on(self):
        self.set('status', 'On')

    def off(self):
        self.set('status', 'Off')
        return

    def prepare(self,  trigger_separation, RO_length, get_t_base=True ):
        '''
        This function needs to be overwritten for the ATS based version of this
        driver
        '''
        if self.AWG!=None:
            if ((self._awg_seq_filename not in self.AWG.get('setup_filename')) and
                    not self._disable_auto_seq_loading):
                self.seq_name = st_seqs.generate_and_upload_marker_sequence(
                    RO_length, trigger_separation, RF_mod=False,
                    IF=self.get('f_RO_mod'), mod_amp=0.5)
            self.AWG.run()
        if get_t_base is True:
            if self.acquisition_instr()==None:
                print('no acquistion prepare')
            elif 'CBox' in self.acquisition_instr():
                trace_length = 512
                tbase = np.arange(0, 5*trace_length, 5)*1e-9
                self.cosI = np.floor(
                    127.*np.cos(2*np.pi*self.get('f_RO_mod')*tbase))
                self.sinI = np.floor(
                    127.*np.sin(2*np.pi*self.get('f_RO_mod')*tbase))
                self._acquisition_instr.sig0_integration_weights(self.cosI)
                self._acquisition_instr.sig1_integration_weights(self.sinI)
                # because using integrated avg
                self._acquisition_instr.set('nr_samples', 1)
                self._acquisition_instr.nr_averages(int(self.nr_averages()))

            elif 'UHFQC' in self.acquisition_instr():
                # self._acquisition_instr.prepare_DSB_weight_and_rotation(
                #     IF=self.get('f_RO_mod'),
                #      weight_function_I=0, weight_function_Q=1)
                # this sets the result to integration and rotation outcome
                self._acquisition_instr.quex_rl_source(2)
                # only one sample to average over
                self._acquisition_instr.quex_rl_length(1)
                self._acquisition_instr.quex_rl_avgcnt(
                    int(np.log2(self.nr_averages())))
                self._acquisition_instr.quex_wint_length(
                    int(RO_length*1.8e9))
                # Configure the result logger to not do any averaging
                # The AWG program uses userregs/0 to define the number o
                # iterations in the loop
                self._acquisition_instr.awgs_0_userregs_0(
                    int(self.nr_averages()))
                # 0 for rl, 1 for iavg
                self._acquisition_instr.awgs_0_userregs_1(0)
                self._acquisition_instr.awgs_0_single(1)
                self._acquisition_instr.acquisition_initialize([0,1], 'rl')
                self.scale_factor = 1/(1.8e9*RO_length*int(self.nr_averages()))


            elif 'ATS' in self.acquisition_instr():
                self._acquisition_instr_controller.demodulation_frequency=self.get('f_RO_mod')
                buffers_per_acquisition = 8
                self._acquisition_instr_controller.update_acquisitionkwargs(#mode='NPT',
                     samples_per_record=64*1000,#4992,
                     records_per_buffer=int(self.nr_averages()/buffers_per_acquisition),#70, segmments
                     buffers_per_acquisition=buffers_per_acquisition,
                     channel_selection='AB',
                     transfer_offset=0,
                     external_startcapture='ENABLED',
                     enable_record_headers='DISABLED',
                     alloc_buffers='DISABLED',
                     fifo_only_streaming='DISABLED',
                     interleave_samples='DISABLED',
                     get_processed_data='DISABLED',
                     allocated_buffers=buffers_per_acquisition,
                     buffer_timeout=1000)

            elif 'DDM' in self.acquisition_instr():

                for i, channel in enumerate([1,2]):
                    eval("self._acquisition_instr.ch_pair1_weight{}_wint_intlength({})".format(channel, RO_length*500e6))
                self._acquisition_instr.ch_pair1_tvmode_naverages(self.nr_averages())
                self._acquisition_instr.ch_pair1_tvmode_nsegments(1)
                self.scale_factor=1/(500e6*RO_length)/127/127*2





        self.LO.on()
        # Changes are now incorporated in the awg seq
        self._awg_seq_parameters_changed = False

        # self.CBox.set('acquisition_mode', 'idle') # aded with xiang

    def probe(self, demodulation_mode='double', **kw):
        '''
        Starts acquisition and returns the data
            'COMP' : returns data as a complex point in the I-Q plane in Volts
        '''
        if self.acquisition_instr()==None:
            dat=[0,0]
            print('no acquistion probe')
        elif 'CBox' in self.acquisition_instr():
            self._acquisition_instr.set('acquisition_mode', 'idle')
            self._acquisition_instr.set(
                'acquisition_mode', 'integration averaging')
            self._acquisition_instr.demodulation_mode(demodulation_mode)
            # d = self.CBox.get_integrated_avg_results()
            # quick fix for spec units. Need to properrly implement it later
            # after this, output is in mV
            scale_factor_dacmV = 1000.*0.75/128.
            # scale_factor_integration = 1./float(self.f_RO_mod()*self.CBox.nr_samples()*5e-9)
            scale_factor_integration = 1. / \
                (64.*self._acquisition_instr.integration_length())
            factor = scale_factor_dacmV*scale_factor_integration
            d = np.double(
                self._acquisition_instr.get_integrated_avg_results())*np.double(factor)
            # print(np.size(d))
            dat = (d[0][0]+1j*d[1][0])
        elif 'UHFQC' in self.acquisition_instr():
            t0 = time.time()
            #self._acquisition_instr.awgs_0_enable(1) #this was causing spikes
            # NH: Reduced timeout to prevent hangups
            dataset = self._acquisition_instr.acquisition_poll(samples=1, acquisition_time=0.001, timeout=10)
            dat = (self.scale_factor*dataset[0][0]+self.scale_factor*1j*dataset[1][0])
            t1 = time.time()
            # print("time for UHFQC polling", t1-t0)
        elif 'ATS' in self.acquisition_instr():
            # t0 = time.time()
            dat = self._acquisition_instr_controller.acquisition()
            # t1 = time.time()
            # print("time for ATS polling", t1-t0)

        elif 'DDM' in self.acquisition_instr():
            # t0 = time.time()
            self._acquisition_instr.ch_pair1_tvmode_enable.set(1)
            self._acquisition_instr.ch_pair1_run.set(1)
            dataI = eval("self._acquisition_instr.ch_pair1_weight{}_tvmode_data()".format(1))
            dataQ = eval("self._acquisition_instr.ch_pair1_weight{}_tvmode_data()".format(2))
            dat = (self.scale_factor*dataI+self.scale_factor*1j*dataQ)
            # t1 = time.time()
            # print("time for DDM polling", t1-t0)
        return dat

    def finish(self):
        if 'UHFQC' in self.acquisition_instr():
            self._acquisition_instr.acquisition_finalize()

    def get_demod_array(self):
        return self.cosI, self.sinI

    def demodulate_data(self, dat):
        '''
        Returns a complex point in the IQ plane by integrating and demodulating
        the data. Demodulation is done based on the 'f_RO_mod' and
        'single_sideband_demod' parameters of the Homodyne instrument.
        '''
        if self._f_RO_mod != 0:
            # self.cosI is based on the time_base and created in self.init()
            if self._single_sideband_demod is True:
                # this definition for demodulation is consistent with
                # issue #131
                I = np.average(self.cosI * dat[0] + self.sinI * dat[1])
                Q = np.average(-self.sinI * dat[0] + self.cosI * dat[1])
            else:  # Single channel demodulation, defaults to using channel 1
                I = 2*np.average(dat[0]*self.cosI)
                Q = 2*np.average(dat[0]*self.sinI)
        else:
            I = np.average(dat[0])
            Q = np.average(dat[1])
        return I+1.j*Q

    def _do_get_acquisition_instr(self):
        # Specifying the int_avg det here should allow replacing it with ATS
        # or potential digitizer acquisition easily
        if self._acquisition_instr==None:
            return None
        else:
            return self._acquisition_instr.name

    def _do_set_acquisition_instr(self, acquisition_instr):
        # Specifying the int_avg det here should allow replacing it with ATS
        # or potential digitizer acquisition easily
        if acquisition_instr==None:
            self._acquisition_instr=None
        else:
            self._acquisition_instr = self.find_instrument(acquisition_instr)

    def _do_get_acquisition_instr_controller(self):
        # Specifying the int_avg det here should allow replacing it with ATS
        # or potential digitizer acquisition easily
        if self._acquisition_instr_controller==None:
            return None
        else:
            return self._acquisition_instr_controller.name

    def _do_set_acquisition_instr_controller(self, acquisition_instr_controller):
        # Specifying the int_avg det here should allow replacing it with ATS
        # or potential digitizer acquisition easily
        if acquisition_instr_controller==None:
            self._acquisition_instr_controller=None
        else:
            self._acquisition_instr_controller = self.find_instrument(acquisition_instr_controller)
            print("controller initialized")


class LO_modulated_Heterodyne(HeterodyneInstrument):

    '''
    Heterodyne instrument for pulse modulated LO.
    Inherits functionality for the HeterodyneInstrument

    AWG is used for modulating signal and triggering the UHFQC or
    CBox is used for acquisition.
    '''
    shared_kwargs = ['RF', 'LO', 'AWG']

    def __init__(self, name,  LO, AWG, acquisition_instr='CBox',
                 single_sideband_demod=False, **kw):
        logging.info(__name__ + ' : Initializing instrument')
        Instrument.__init__(self, name, **kw)
        self.LO = LO
        self.AWG = AWG
        self._awg_seq_filename = 'Heterodyne_marker_seq_RF_mod'
        self.add_parameter('frequency',
                           label='Heterodyne frequency',
                           unit='Hz',
                           get_cmd=self.do_get_frequency,
                           set_cmd=self.do_set_frequency,
                           vals=vals.Numbers(9e3, 40e9))
        self.add_parameter('f_RO_mod',
                           set_cmd=self.do_set_f_RO_mod,
                           get_cmd=self.do_get_f_RO_mod,
                           vals=vals.Numbers(-200e6, 200e6),
                           label='Intermodulation frequency',
                           unit='Hz')
        self.add_parameter('single_sideband_demod',
                           label='Single sideband demodulation',
                           get_cmd=self.do_get_single_sideband_demod,
                           set_cmd=self.do_set_single_sideband_demod)
        self.set('single_sideband_demod', single_sideband_demod)

        self.add_parameter('mod_amp',
                           label='Modulation amplitud',
                           unit='V',
                           set_cmd=self._do_set_mod_amp,
                           get_cmd=self._do_get_mod_amp,
                           vals=vals.Numbers(0, 1))

        self.add_parameter('acquisition_instr',
                           set_cmd=self._do_set_acquisition_instr,
                           get_cmd=self._do_get_acquisition_instr,
                           vals=vals.Strings())

        self.add_parameter('nr_averages',
                           parameter_class=ManualParameter,
                           initial_value=1024,
                           vals=vals.Numbers(min_value=0, max_value=1e6))
        # Negative vals should be done by setting the f_RO_mod negative

        self._f_RO_mod = 0  # ensures that awg_seq_par_changed flag is True
        self._mod_amp = .5
        self._frequency = None
        self.set('f_RO_mod', -10e6)
        self.set('mod_amp', .5)
        self._disable_auto_seq_loading = True
        self._awg_seq_parameters_changed = True
        self._mod_amp_changed = True
        self.acquisition_instr(acquisition_instr)
        # internally used to reload awg sequence implicitly

    def prepare(self, get_t_base=True):
        '''
        This function needs to be overwritten for the ATS based version of this
        driver

        Sets parameters in the ATS_CW and turns on the sources.
        if optimize == True it will optimze the acquisition time for a fixed
        t_int.
        '''
        # only uploads a seq to AWG if something changed
        if ((self._awg_seq_filename not in self.AWG.get('setup_filename') or
                self._awg_seq_parameters_changed) and
                not self._disable_auto_seq_loading):
            self.seq_name = st_seqs.generate_and_upload_marker_sequence(
                50e-9, 5e-6, RF_mod=True,
                IF=self.get('f_RO_mod'), mod_amp=0.5)

        self.AWG.run()

        if get_t_base is True:
            trace_length = self.CBox.get('nr_samples')
            tbase = np.arange(0, 5*trace_length, 5)*1e-9
            self.cosI = np.cos(2*np.pi*self.get('f_RO_mod')*tbase)
            self.sinI = np.sin(2*np.pi*self.get('f_RO_mod')*tbase)
        self.LO.on()
        # Changes are now incorporated in the awg seq
        self._awg_seq_parameters_changed = False

        self.CBox.set('nr_samples', 1)  # because using integrated avg

    def do_set_frequency(self, val):
        self._frequency = val
        # this is the definition agreed upon in issue 131
        # AWG modulation ensures that signal ends up at RF-frequency
        self.LO.set('frequency', val-self.f_RO_mod.get())

    def do_get_frequency(self):
        LO_freq = self.LO.get('frequency')
        freq = LO_freq + self._f_RO_mod
        return freq

    def probe(self):
        # Split up in here to prevent unneedy
        if self._mod_amp_changed:
            self.AWG.set('ch3_amp', self.get('mod_amp'))
            self.AWG.set('ch4_amp', self.get('mod_amp'))
        if self._awg_seq_parameters_changed:
            self.prepare()
        self.CBox.set('acquisition_mode', 0)
        self.CBox.set('acquisition_mode', 4)
        d = self.CBox.get_integrated_avg_results()
        dat = d[0][0]+1j*d[1][0]
        return dat

    def _do_set_mod_amp(self, val):
        self._mod_amp = val
        self._mod_amp_changed = True

    def _do_get_mod_amp(self):
        return self._mod_amp

    def do_set_f_RO_mod(self, val):
        if val != self._f_RO_mod:
            self._awg_seq_parameters_changed = True
        self._f_RO_mod = val

    def _do_get_acquisition_instr(self):
        # Specifying the int_avg det here should allow replacing it with ATS
        # or potential digitizer acquisition easily
        return self._acquisition_instr.name

    def _do_set_acquisition_instr(self, acquisition_instr):
        # Specifying the int_avg det here should allow replacing it with ATS
        # or potential digitizer acquisition easily

        self._acquisition_instr = self.find_instrument(acquisition_instr)
