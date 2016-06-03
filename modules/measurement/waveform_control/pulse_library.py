import numpy as np
'''
Library containing pulse shapes.
'''


from modules.measurement.waveform_control.pulse import Pulse, apply_modulation


class MW_IQmod_pulse(Pulse):
    '''
    Block pulse on the I channel modulated with IQ modulation.

    kwargs:
        amplitude (V)
        length (s)
        mod_frequency (Hz)
        phase (deg)
        phaselock (bool)

    I_env is a block pulse
    transformation:
    [I_mod] = [cos(wt+phi)   0] [I_env]
    [Q_mod]   [-sin(wt+phi)  0] [0]
    '''
    def __init__(self, name, I_channel, Q_channel, **kw):
        super().__init__(name)
        self.I_channel = I_channel
        self.Q_channel = Q_channel
        self.channels = [I_channel, Q_channel]

        self.mod_frequency = kw.pop('mod_frequency', 1e6)
        self.amplitude = kw.pop('amplitude', 0.1)
        self.length = kw.pop('length', 1e-6)
        self.phase = kw.pop('phase', 0.)
        self.phaselock = kw.pop('phaselock', True)
        self.alpha = kw.pop('alpha', 1)
        self.phi_skew = kw.pop('phi_skew', 0)

    def __call__(self, **kw):
        self.mod_frequency = kw.pop('mod_frequency', self.mod_frequency)
        self.amplitude = kw.pop('amplitude', self.amplitude)
        self.length = kw.pop('length', self.length)
        self.phase = kw.pop('phase', self.phase)
        self.phaselock = kw.pop('phaselock', self.phaselock)
        self.alpha = kw.pop('alpha', self.alpha)
        self.phi_skew = kw.pop('phi_skew', self.phi_skew)
        return self

    def chan_wf(self, chan, tvals):
        idx0 = np.where(tvals >= tvals[0])[0][0]
        idx1 = np.where(tvals <= tvals[0] + self.length)[0][-1] + 1
        wf = np.zeros(len(tvals))
        if not self.phaselock:
            tvals = tvals.copy() - tvals[idx0]
        I_mod, Q_mod = apply_modulation(
            np.ones(len(tvals)), np.zeros(len(tvals)), tvals[idx0:idx1],
            mod_frequency=self.mod_frequency, phase=self.phase,
            phi_skew=self.phi_skew, alpha=self.alpha)
        if chan == self.I_channel:
            wf[idx0:idx1] += I_mod
        elif chan == self.Q_channel:
            wf[idx0:idx1] += Q_mod
        return wf


class SSB_DRAG_pulse(Pulse):
    '''
    Gauss pulse on the I channel, derivative of Gauss on the Q channel.
    modulated with Single Sideband (SSB)  modulation.

    Required arguments:
        name (str) : base name of the pulse
        I_channel (str) : name of the channel on which to act (as defined in pular)
        Q_channel (str) : " "

    kwargs:
        amplitude (V)
        sigma (s)
        nr_sigma (int) (default=4)
        motzoi ( ) (default=0)

        mod_frequency (Hz)
        phase (deg)
        phaselock (bool)

        alpha (arb. units): QI amplitude
        phi_skew (deg) :    phase skewness

    I_env is a gaussian
    Q_env is the derivative of a gaussian
    The envelope is transformation:
    Signal = predistortion * modulation * envelope

    See Leo's notes on mixer predistortion in the docs for details

    [I_mod] = [1        tan(phi-skew)] [cos(wt+phi)   sin(wt+phi)] [I_env]
    [Q_mod]   [0  sec(phi-skew)/alpha] [-sin(wt+phi)  cos(wt+phi)] [Q_env]


    The predistortion * modulation matrix is implemented in a single step using
    the following matrix

    M*mod = [cos(x)-tan(phi-skew)sin(x)      sin(x)+tan(phi-skew)cos(x) ]
            [-sin(x)sec(phi-skew)/alpha  cos(x)sec(phi-skew)/alpha]

    where: x = wt+phi

    Reduces to a Gaussian pulse if motzoi == 0
    Reduces to an unmodulated pulse if mod_frequency == 0
    '''
    def __init__(self, name, I_channel, Q_channel, **kw):
        super().__init__(name)
        self.I_channel = I_channel
        self.Q_channel = Q_channel
        self.channels = [I_channel, Q_channel]

        self.amplitude = kw.pop('amplitude', 0.1)
        self.sigma = kw.pop('sigma', 0.25e-6)
        self.nr_sigma = kw.pop('nr_sigma', 4)
        self.motzoi = kw.pop('motzoi', 0)

        self.mod_frequency = kw.pop('mod_frequency', 1e6)
        self.phase = kw.pop('phase', 0.)
        self.phaselock = kw.pop('phaselock', True)

        self.alpha = kw.pop('alpha', 1)        # QI amp ratio
        self.phi_skew = kw.pop('phi_skew', 0)  # IQ phase skewness

        self.length = self.sigma * self.nr_sigma

    def __call__(self, **kw):
        self.amplitude = kw.pop('amplitude', self.amplitude)
        self.sigma = kw.pop('sigma', self.sigma)
        self.nr_sigma = kw.pop('nr_sigma', self.nr_sigma)
        self.motzoi = kw.pop('motzoi', self.motzoi)
        self.mod_frequency = kw.pop('mod_frequency', self.mod_frequency)
        self.phase = kw.pop('phase', self.phase)
        self.phaselock = kw.pop('phaselock', self.phaselock)

        self.length = self.sigma * self.nr_sigma
        return self

    def chan_wf(self, chan, tvals):
        idx0 = np.where(tvals >= tvals[0])[0][0]
        idx1 = np.where(tvals <= tvals[0] + self.length)[0][-1] + 1
        wf = np.zeros(len(tvals))
        t = tvals - tvals[0]  # Gauss envelope should not be displaced
        mu = self.length/2.0
        if not self.phaselock:
            tvals = tvals.copy() - tvals[idx0]

        gauss_env = self.amplitude*np.exp(-(0.5 * ((t-mu)**2) / self.sigma**2))
        deriv_gauss_env = self.motzoi * -1 * (t-mu)/(self.sigma**1) * gauss_env
        # substract offsets
        gauss_env -= (gauss_env[0]+gauss_env[-1])/2.
        deriv_gauss_env -= (deriv_gauss_env[0]+deriv_gauss_env[-1])/2.

        # Note prefactor is multiplied by self.sigma to normalize
        if chan == self.I_channel:
            I_mod, Q_mod = apply_modulation(gauss_env, deriv_gauss_env,
                                            tvals[idx0:idx1],
                                            mod_frequency=self.mod_frequency,
                                            phase=self.phase,
                                            phi_skew=self.phi_skew,
                                            alpha=self.alpha)
            wf[idx0:idx1] += I_mod

        if chan == self.Q_channel:
            I_mod, Q_mod = apply_modulation(gauss_env, deriv_gauss_env,
                                            tvals[idx0:idx1],
                                            mod_frequency=self.mod_frequency,
                                            phase=self.phase,
                                            phi_skew=self.phi_skew,
                                            alpha=self.alpha)
            wf[idx0:idx1] += Q_mod

        return wf


class Mux_DRAG_pulse(SSB_DRAG_pulse):
    '''
    Uses 4 AWG channels to play a multiplexer compatible SSB DRAG pulse
    uses channels GI and GQ (default 1 and 2) for the SSB-modulated gaussian
    and uses channels DI and DQ (default 3 and 4) for the modulated derivative
    components.
    '''
    def __init__(self, name, GI_channel='ch1', GQ_channel='ch2',
                 DI_channel='ch3', DQ_channel='ch4', **kw):
        # Ideally I'd use grandparent inheritance here but I couldn't get it
        # to work
        self.name = name
        self.start_offset = 0
        self.stop_offset = 0
        self._t0 = None
        self._clock = None

        self.GI_channel = GI_channel
        self.GQ_channel = GQ_channel
        self.DI_channel = DI_channel
        self.DQ_channel = DQ_channel
        self.channels = [GI_channel, GQ_channel, DI_channel, DQ_channel]
        self.amplitude = kw.pop('amplitude', 0.1)
        self.sigma = kw.pop('sigma', 0.25e-6)
        self.nr_sigma = kw.pop('nr_sigma', 4)
        self.motzoi = kw.pop('motzoi', 1)

        self.mod_frequency = kw.pop('mod_frequency', 1e6)
        self.phase = kw.pop('phase', 0.)
        self.phaselock = kw.pop('phaselock', True)

        # skewness parameters
        self.G_alpha = kw.pop('G_alpha', 1)        # QI amp ratio of Gauss
        self.G_phi_skew = kw.pop('G_phi_skew', 0)  # IQ phase skewness of Gauss
        self.D_alpha = kw.pop('D_alpha', 1)        # QI amp ratio of deriv
        self.D_phi_skew = kw.pop('D_phi_skew', 0)  # IQ phase skewness of deriv

        self.length = self.sigma * self.nr_sigma

    def __call__(self, **kw):
        self.GI_channel = kw.pop('GI_channel', self.GI_channel)
        self.GQ_channel = kw.pop('GQ_channel', self.GQ_channel)
        self.DI_channel = kw.pop('DI_channel', self.DI_channel)
        self.DQ_channel = kw.pop('DQ_channel', self.DQ_channel)
        self.channels = [self.GI_channel, self.GQ_channel,
                         self.DI_channel, self.DQ_channel]
        self.amplitude = kw.pop('amplitude', self.amplitude)
        self.sigma = kw.pop('sigma', self.sigma)
        self.nr_sigma = kw.pop('nr_sigma', self.nr_sigma)

        self.mod_frequency = kw.pop('mod_frequency', self.mod_frequency)
        self.phase = kw.pop('phase', self.phase)
        self.phaselock = kw.pop('phaselock', self.phaselock)

        # skewness parameters
        self.G_alpha = kw.pop('G_alpha', self.G_alpha)        # QI amp ratio
        self.G_phi_skew = kw.pop('G_phi_skew', self.G_phi_skew)  # IQ phase skewness
        self.D_alpha = kw.pop('D_alpha', self.D_alpha)
        self.D_phi_skew = kw.pop('D_phi_skew', self.D_phi_skew)

        self.length = self.sigma * self.nr_sigma
        return self

    def chan_wf(self, chan, tvals):
        idx0 = np.where(tvals >= tvals[0])[0][0]
        idx1 = np.where(tvals <= tvals[0] + self.length)[0][-1] + 1
        wf = np.zeros(len(tvals))
        t = tvals - tvals[0]  # Gauss envelope should not be displaced
        mu = self.length/2.0
        if not self.phaselock:
            tvals = tvals.copy() - tvals[idx0]

        gauss_env = self.amplitude*np.exp(-(0.5 * ((t-mu)**2) / self.sigma**2))
        if chan in [self.GI_channel, self.GQ_channel]:
            gauss_env -= (gauss_env[0]+gauss_env[-1])/2.
            I_mod, Q_mod = apply_modulation(gauss_env,
                                            np.zeros(len(tvals)),
                                            tvals[idx0:idx1],
                                            mod_frequency=self.mod_frequency,
                                            phase=self.phase,
                                            phi_skew=self.G_phi_skew,
                                            alpha=self.G_alpha)
            if chan == self.GI_channel:
                wf[idx0:idx1] += I_mod
            else:
                wf[idx0:idx1] += Q_mod

        elif chan in [self.DI_channel, self.DQ_channel]:
            der_env = self.motzoi * -1 * (t-mu)/(self.sigma**1) * gauss_env
            der_env -= (der_env[0]+der_env[-1])/2.
            I_mod, Q_mod = apply_modulation(np.zeros(len(tvals)), der_env,
                                            tvals[idx0:idx1],
                                            mod_frequency=self.mod_frequency,
                                            phase=self.phase,
                                            phi_skew=self.D_phi_skew,
                                            alpha=self.D_alpha)
            if chan == self.DI_channel:
                wf[idx0:idx1] += I_mod
            else:
                wf[idx0:idx1] += Q_mod
        return wf

