# Authors: Alexandre Gramfort <alexandre.gramfort@telecom-paristech.fr>
#          Denis Engemann <denis.engemann@gmail.com>
#          Martin Luessi <mluessi@nmr.mgh.harvard.edu>
#          Eric Larson <larson.eric.d@gmail.com>
#
# License: Simplified BSD

import os.path as op
from functools import partial

import numpy as np
from numpy.testing import assert_array_equal, assert_equal
import pytest
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib.patches import Circle

from mne import (read_evokeds, read_proj, make_fixed_length_events, Epochs,
                 compute_proj_evoked, find_layout)
from mne.io.proj import make_eeg_average_ref_proj
from mne.io import read_raw_fif, read_info
from mne.io.constants import FIFF
from mne.io.pick import pick_info, channel_indices_by_type
from mne.io.compensator import get_current_comp
from mne.io.proj import Projection
from mne.channels import read_layout, make_eeg_layout
from mne.datasets import testing
from mne.time_frequency.tfr import AverageTFR
from mne.utils import run_tests_if_main

from mne.viz import plot_evoked_topomap, plot_projs_topomap
from mne.viz.topomap import (_check_outlines, _onselect, plot_topomap,
                             plot_arrowmap, plot_psds_topomap)
from mne.viz.utils import _find_peaks, _fake_click


data_dir = testing.data_path(download=False)
subjects_dir = op.join(data_dir, 'subjects')
ecg_fname = op.join(data_dir, 'MEG', 'sample', 'sample_audvis_ecg-proj.fif')
triux_fname = op.join(data_dir, 'SSS', 'TRIUX', 'triux_bmlhus_erm_raw.fif')

base_dir = op.join(op.dirname(__file__), '..', '..', 'io', 'tests', 'data')
evoked_fname = op.join(base_dir, 'test-ave.fif')
raw_fname = op.join(base_dir, 'test_raw.fif')
event_name = op.join(base_dir, 'test-eve.fif')
ctf_fname = op.join(base_dir, 'test_ctf_comp_raw.fif')
layout = read_layout('Vectorview-all')


def test_plot_topomap_interactive():
    """Test interactive topomap projection plotting."""
    evoked = read_evokeds(evoked_fname, baseline=(None, 0))[0]
    evoked.pick_types(meg='mag')
    evoked.info['projs'] = []
    assert not evoked.proj
    evoked.add_proj(compute_proj_evoked(evoked, n_mag=1))

    plt.close('all')
    fig = Figure()
    canvas = FigureCanvas(fig)
    ax = fig.gca()

    kwargs = dict(vmin=-240, vmax=240, times=[0.1], colorbar=False, axes=ax,
                  res=8, time_unit='s')
    evoked.copy().plot_topomap(proj=False, **kwargs)
    canvas.draw()
    image_noproj = np.frombuffer(canvas.tostring_rgb(), dtype='uint8')
    assert len(plt.get_fignums()) == 1

    ax.clear()
    evoked.copy().plot_topomap(proj=True, **kwargs)
    canvas.draw()
    image_proj = np.frombuffer(canvas.tostring_rgb(), dtype='uint8')
    assert not np.array_equal(image_noproj, image_proj)
    assert len(plt.get_fignums()) == 1

    ax.clear()
    evoked.copy().plot_topomap(proj='interactive', **kwargs)
    canvas.draw()
    image_interactive = np.frombuffer(canvas.tostring_rgb(), dtype='uint8')
    assert_array_equal(image_noproj, image_interactive)
    assert not np.array_equal(image_proj, image_interactive)
    assert len(plt.get_fignums()) == 2

    proj_fig = plt.figure(plt.get_fignums()[-1])
    _fake_click(proj_fig, proj_fig.axes[0], [0.5, 0.5], xform='data')
    canvas.draw()
    image_interactive_click = np.frombuffer(
        canvas.tostring_rgb(), dtype='uint8')
    assert_array_equal(image_proj, image_interactive_click)
    assert not np.array_equal(image_noproj, image_interactive_click)

    _fake_click(proj_fig, proj_fig.axes[0], [0.5, 0.5], xform='data')
    canvas.draw()
    image_interactive_click = np.frombuffer(
        canvas.tostring_rgb(), dtype='uint8')
    assert_array_equal(image_noproj, image_interactive_click)
    assert not np.array_equal(image_proj, image_interactive_click)


@testing.requires_testing_data
def test_plot_projs_topomap():
    """Test plot_projs_topomap."""
    projs = read_proj(ecg_fname)
    info = read_info(raw_fname)
    fast_test = {"res": 8, "contours": 0, "sensors": False}
    plot_projs_topomap(projs, info=info, colorbar=True, **fast_test)
    plt.close('all')
    ax = plt.subplot(111)
    projs[3].plot_topomap()
    plot_projs_topomap(projs[:1], axes=ax, **fast_test)  # test axes param
    plt.close('all')
    plot_projs_topomap(read_info(triux_fname)['projs'][-1:], **fast_test)
    plt.close('all')
    plot_projs_topomap(read_info(triux_fname)['projs'][:1], ** fast_test)
    plt.close('all')
    eeg_avg = make_eeg_average_ref_proj(info)
    pytest.raises(RuntimeError, eeg_avg.plot_topomap)  # no layout
    eeg_avg.plot_topomap(info=info, **fast_test)
    plt.close('all')


@pytest.mark.slowtest
@testing.requires_testing_data
def test_plot_topomap():
    """Test topomap plotting."""
    # evoked
    res = 8
    fast_test = dict(res=res, contours=0, sensors=False, time_unit='s')
    fast_test_noscale = dict(res=res, contours=0, sensors=False)
    evoked = read_evokeds(evoked_fname, 'Left Auditory',
                          baseline=(None, 0))

    # Test animation
    _, anim = evoked.animate_topomap(ch_type='grad', times=[0, 0.1],
                                     butterfly=False, time_unit='s')
    anim._func(1)  # _animate has to be tested separately on 'Agg' backend.
    plt.close('all')

    ev_bad = evoked.copy().pick_types(meg=False, eeg=True)
    ev_bad.pick_channels(ev_bad.ch_names[:2])
    plt_topomap = partial(ev_bad.plot_topomap, **fast_test)
    plt_topomap(times=ev_bad.times[:2] - 1e-6)  # auto, plots EEG
    pytest.raises(ValueError, plt_topomap, ch_type='mag')
    pytest.raises(TypeError, plt_topomap, head_pos='foo')
    pytest.raises(KeyError, plt_topomap, head_pos=dict(foo='bar'))
    pytest.raises(ValueError, plt_topomap, head_pos=dict(center=0))
    pytest.raises(ValueError, plt_topomap, times=[-100])  # bad time
    pytest.raises(ValueError, plt_topomap, times=[[0]])  # bad time

    evoked.plot_topomap([0.1], ch_type='eeg', scalings=1, res=res,
                        contours=[-100, 0, 100], time_unit='ms')

    # extrapolation to the edges of the convex hull or the head circle
    evoked.plot_topomap([0.1], ch_type='eeg', scalings=1, res=res,
                        contours=[-100, 0, 100], time_unit='ms',
                        extrapolate='local')
    evoked.plot_topomap([0.1], ch_type='eeg', scalings=1, res=res,
                        contours=[-100, 0, 100], time_unit='ms',
                        extrapolate='head')
    evoked.plot_topomap([0.1], ch_type='eeg', scalings=1, res=res,
                        contours=[-100, 0, 100], time_unit='ms',
                        extrapolate='head', outlines='skirt')

    # extrapolation options when < 4 channels:
    temp_data = np.random.random(3)
    picks = channel_indices_by_type(evoked.info)['mag'][:3]
    info_sel = pick_info(evoked.info, picks)
    plot_topomap(temp_data, info_sel, extrapolate='local', res=res)
    plot_topomap(temp_data, info_sel, extrapolate='head', res=res)

    plt_topomap = partial(evoked.plot_topomap, **fast_test)
    plt_topomap(0.1, layout=layout, scalings=dict(mag=0.1))
    plt.close('all')
    axes = [plt.subplot(221), plt.subplot(222)]
    plt_topomap(axes=axes, colorbar=False)
    plt.close('all')
    plt_topomap(times=[-0.1, 0.2])
    plt.close('all')
    evoked_grad = evoked.copy().crop(0, 0).pick_types(meg='grad')
    mask = np.zeros((204, 1), bool)
    mask[[0, 3, 5, 6]] = True
    names = []

    def proc_names(x):
        names.append(x)
        return x[4:]

    evoked_grad.plot_topomap(ch_type='grad', times=[0], mask=mask,
                             show_names=proc_names, **fast_test)
    assert_equal(sorted(names),
                 ['MEG 011x', 'MEG 012x', 'MEG 013x', 'MEG 014x'])
    mask = np.zeros_like(evoked.data, dtype=bool)
    mask[[1, 5], :] = True
    plt_topomap(ch_type='mag', outlines=None)
    times = [0.1]
    plt_topomap(times, ch_type='grad', mask=mask)
    plt_topomap(times, ch_type='planar1')
    plt_topomap(times, ch_type='planar2')
    plt_topomap(times, ch_type='grad', mask=mask, show_names=True,
                mask_params={'marker': 'x'})
    plt.close('all')
    pytest.raises(ValueError, plt_topomap, times, ch_type='eeg', average=-1e3)
    pytest.raises(ValueError, plt_topomap, times, ch_type='eeg', average='x')

    p = plt_topomap(times, ch_type='grad', image_interp='bilinear',
                    show_names=lambda x: x.replace('MEG', ''))
    subplot = [x for x in p.get_children() if 'Subplot' in str(type(x))]
    assert len(subplot) >= 1, [type(x) for x in p.get_children()]
    subplot = subplot[0]

    have_all = all('MEG' not in x.get_text()
                   for x in subplot.get_children()
                   if isinstance(x, matplotlib.text.Text))
    assert have_all

    # Plot array
    for ch_type in ('mag', 'grad'):
        evoked_ = evoked.copy().pick_types(eeg=False, meg=ch_type)
        plot_topomap(evoked_.data[:, 0], evoked_.info, **fast_test_noscale)
    # fail with multiple channel types
    pytest.raises(ValueError, plot_topomap, evoked.data[0, :], evoked.info)

    # Test title
    def get_texts(p):
        return [x.get_text() for x in p.get_children() if
                isinstance(x, matplotlib.text.Text)]

    p = plt_topomap(times, ch_type='eeg', average=0.01)
    assert_equal(len(get_texts(p)), 0)
    p = plt_topomap(times, ch_type='eeg', title='Custom')
    texts = get_texts(p)
    assert_equal(len(texts), 1)
    assert_equal(texts[0], 'Custom')
    plt.close('all')

    # delaunay triangulation warning
    plt_topomap(times, ch_type='mag', layout=None)
    # projs have already been applied
    pytest.raises(RuntimeError, plot_evoked_topomap, evoked, 0.1, 'mag',
                  proj='interactive', time_unit='s')

    # change to no-proj mode
    evoked = read_evokeds(evoked_fname, 'Left Auditory',
                          baseline=(None, 0), proj=False)
    fig1 = evoked.plot_topomap('interactive', 'mag', proj='interactive',
                               **fast_test)
    _fake_click(fig1, fig1.axes[1], (0.5, 0.5))  # click slider
    data_max = np.max(fig1.axes[0].images[0]._A)
    fig2 = plt.gcf()
    _fake_click(fig2, fig2.axes[0], (0.075, 0.775))  # toggle projector
    # make sure projector gets toggled
    assert (np.max(fig1.axes[0].images[0]._A) != data_max)

    pytest.raises(RuntimeError, plot_evoked_topomap, evoked,
                  np.repeat(.1, 50), time_unit='s')
    pytest.raises(ValueError, plot_evoked_topomap, evoked, [-3e12, 15e6],
                  time_unit='s')

    for ch in evoked.info['chs']:
        if ch['coil_type'] == FIFF.FIFFV_COIL_EEG:
            ch['loc'].fill(0)

    # Remove extra digitization point, so EEG digitization points
    # correspond with the EEG electrodes
    del evoked.info['dig'][85]

    pos = make_eeg_layout(evoked.info).pos[:, :2]
    pos, outlines = _check_outlines(pos, 'head')
    assert ('head' in outlines.keys())
    assert ('nose' in outlines.keys())
    assert ('ear_left' in outlines.keys())
    assert ('ear_right' in outlines.keys())
    assert ('autoshrink' in outlines.keys())
    assert (outlines['autoshrink'])
    assert ('clip_radius' in outlines.keys())
    assert_array_equal(outlines['clip_radius'], 0.5)

    pos, outlines = _check_outlines(pos, 'skirt')
    assert ('head' in outlines.keys())
    assert ('nose' in outlines.keys())
    assert ('ear_left' in outlines.keys())
    assert ('ear_right' in outlines.keys())
    assert ('autoshrink' in outlines.keys())
    assert (not outlines['autoshrink'])
    assert ('clip_radius' in outlines.keys())
    assert_array_equal(outlines['clip_radius'], 0.625)

    pos, outlines = _check_outlines(pos, 'skirt',
                                    head_pos={'scale': [1.2, 1.2]})
    assert_array_equal(outlines['clip_radius'], 0.75)

    # Plot skirt
    evoked.plot_topomap(times, ch_type='eeg', outlines='skirt', **fast_test)

    # Pass custom outlines without patch
    evoked.plot_topomap(times, ch_type='eeg', outlines=outlines, **fast_test)
    plt.close('all')

    # Test interactive cmap
    fig = plot_evoked_topomap(evoked, times=[0., 0.1], ch_type='eeg',
                              cmap=('Reds', True), title='title', **fast_test)
    fig.canvas.key_press_event('up')
    fig.canvas.key_press_event(' ')
    fig.canvas.key_press_event('down')
    cbar = fig.get_axes()[0].CB  # Fake dragging with mouse.
    ax = cbar.cbar.ax
    _fake_click(fig, ax, (0.1, 0.1))
    _fake_click(fig, ax, (0.1, 0.2), kind='motion')
    _fake_click(fig, ax, (0.1, 0.3), kind='release')

    _fake_click(fig, ax, (0.1, 0.1), button=3)
    _fake_click(fig, ax, (0.1, 0.2), button=3, kind='motion')
    _fake_click(fig, ax, (0.1, 0.3), kind='release')

    fig.canvas.scroll_event(0.5, 0.5, -0.5)  # scroll down
    fig.canvas.scroll_event(0.5, 0.5, 0.5)  # scroll up

    plt.close('all')

    # Pass custom outlines with patch callable
    def patch():
        return Circle((0.5, 0.4687), radius=.46,
                      clip_on=True, transform=plt.gca().transAxes)
    outlines['patch'] = patch
    plot_evoked_topomap(evoked, times, ch_type='eeg', outlines=outlines,
                        **fast_test)

    # Remove digitization points. Now topomap should fail
    evoked.info['dig'] = None
    pytest.raises(RuntimeError, plot_evoked_topomap, evoked,
                  times, ch_type='eeg', time_unit='s')
    plt.close('all')

    # Error for missing names
    n_channels = len(pos)
    data = np.ones(n_channels)
    pytest.raises(ValueError, plot_topomap, data, pos, show_names=True)

    # Test error messages for invalid pos parameter
    pos_1d = np.zeros(n_channels)
    pos_3d = np.zeros((n_channels, 2, 2))
    pytest.raises(ValueError, plot_topomap, data, pos_1d)
    pytest.raises(ValueError, plot_topomap, data, pos_3d)
    pytest.raises(ValueError, plot_topomap, data, pos[:3, :])

    pos_x = pos[:, :1]
    pos_xyz = np.c_[pos, np.zeros(n_channels)[:, np.newaxis]]
    pytest.raises(ValueError, plot_topomap, data, pos_x)
    pytest.raises(ValueError, plot_topomap, data, pos_xyz)

    # An #channels x 4 matrix should work though. In this case (x, y, width,
    # height) is assumed.
    pos_xywh = np.c_[pos, np.zeros((n_channels, 2))]
    plot_topomap(data, pos_xywh)
    plt.close('all')

    # Test peak finder
    axes = [plt.subplot(131), plt.subplot(132)]
    evoked.plot_topomap(times='peaks', axes=axes, **fast_test)
    plt.close('all')
    evoked.data = np.zeros(evoked.data.shape)
    evoked.data[50][1] = 1
    assert_array_equal(_find_peaks(evoked, 10), evoked.times[1])
    evoked.data[80][100] = 1
    assert_array_equal(_find_peaks(evoked, 10), evoked.times[[1, 100]])
    evoked.data[2][95] = 2
    assert_array_equal(_find_peaks(evoked, 10), evoked.times[[1, 95]])
    assert_array_equal(_find_peaks(evoked, 1), evoked.times[95])

    # Test excluding bads channels
    evoked_grad.info['bads'] += [evoked_grad.info['ch_names'][0]]
    orig_bads = evoked_grad.info['bads']
    evoked_grad.plot_topomap(ch_type='grad', times=[0], time_unit='ms')
    assert_array_equal(evoked_grad.info['bads'], orig_bads)
    plt.close('all')


def test_plot_tfr_topomap():
    """Test plotting of TFR data."""
    raw = read_raw_fif(raw_fname)
    times = np.linspace(-0.1, 0.1, 200)
    res = 8
    n_freqs = 3
    nave = 1
    rng = np.random.RandomState(42)
    picks = [93, 94, 96, 97, 21, 22, 24, 25, 129, 130, 315, 316, 2, 5, 8, 11]
    info = pick_info(raw.info, picks)
    data = rng.randn(len(picks), n_freqs, len(times))
    tfr = AverageTFR(info, data, times, np.arange(n_freqs), nave)
    tfr.plot_topomap(ch_type='mag', tmin=0.05, tmax=0.150, fmin=0, fmax=10,
                     res=res, contours=0)

    eclick = matplotlib.backend_bases.MouseEvent(
        'button_press_event', plt.gcf().canvas, 0, 0, 1)
    eclick.xdata = eclick.ydata = 0.1
    eclick.inaxes = plt.gca()
    erelease = matplotlib.backend_bases.MouseEvent(
        'button_release_event', plt.gcf().canvas, 0.9, 0.9, 1)
    erelease.xdata = 0.3
    erelease.ydata = 0.2
    pos = [[0.11, 0.11], [0.25, 0.5], [0.0, 0.2], [0.2, 0.39]]
    _onselect(eclick, erelease, tfr, pos, 'grad', 1, 3, 1, 3, 'RdBu_r', list())
    _onselect(eclick, erelease, tfr, pos, 'mag', 1, 3, 1, 3, 'RdBu_r', list())
    eclick.xdata = eclick.ydata = 0.
    erelease.xdata = erelease.ydata = 0.9
    tfr._onselect(eclick, erelease, None, 'mean', None)
    plt.close('all')

    # test plot_psds_topomap
    info = raw.info.copy()
    chan_inds = channel_indices_by_type(info)
    info = pick_info(info, chan_inds['grad'][:4])

    fig, axes = plt.subplots()
    freqs = np.arange(3., 9.5)
    bands = [(4, 8, 'Theta')]
    psd = np.random.rand(len(info['ch_names']), freqs.shape[0])
    plot_psds_topomap(psd, freqs, info, bands=bands, axes=[axes])


def test_ctf_plotting():
    """Test CTF topomap plotting."""
    raw = read_raw_fif(ctf_fname, preload=True)
    assert raw.compensation_grade == 3
    events = make_fixed_length_events(raw, duration=0.01)
    assert len(events) > 10
    evoked = Epochs(raw, events, tmin=0, tmax=0.01, baseline=None).average()
    assert get_current_comp(evoked.info) == 3
    # smoke test that compensation does not matter
    evoked.plot_topomap(time_unit='s')
    # better test that topomaps can still be used without plotting ref
    evoked.pick_types(meg=True, ref_meg=False)
    evoked.plot_topomap()


@pytest.mark.slowtest  # can be slow on OSX
@testing.requires_testing_data
def test_plot_arrowmap():
    """Test arrowmap plotting."""
    evoked = read_evokeds(evoked_fname, 'Left Auditory',
                          baseline=(None, 0))
    with pytest.raises(ValueError, match='Multiple channel types'):
        plot_arrowmap(evoked.data[:, 0], evoked.info)
    evoked_eeg = evoked.copy().pick_types(meg=False, eeg=True)
    with pytest.raises(ValueError, match='Multiple channel types'):
        plot_arrowmap(evoked_eeg.data[:, 0], evoked.info)
    evoked_mag = evoked.copy().pick_types(meg='mag')
    evoked_grad = evoked.copy().pick_types(meg='grad')
    plot_arrowmap(evoked_mag.data[:, 0], evoked_mag.info)
    plot_arrowmap(evoked_grad.data[:, 0], evoked_grad.info,
                  info_to=evoked_mag.info)


@testing.requires_testing_data
def test_plot_topomap_neuromag122():
    """Test topomap plotting."""
    res = 8
    fast_test = dict(res=res, contours=0, sensors=False)
    evoked = read_evokeds(evoked_fname, 'Left Auditory',
                          baseline=(None, 0))
    evoked.pick_types(meg='grad')
    evoked.pick_channels(evoked.ch_names[:122])
    ch_names = ['MEG %03d' % k for k in range(1, 123)]
    for c in evoked.info['chs']:
        c['coil_type'] = FIFF.FIFFV_COIL_NM_122
    evoked.rename_channels({c_old: c_new for (c_old, c_new) in
                            zip(evoked.ch_names, ch_names)})
    layout = find_layout(evoked.info)
    assert layout.kind.startswith('Neuromag_122')
    evoked.plot_topomap(times=[0.1], **fast_test)

    proj = Projection(active=False,
                      desc="test", kind=1,
                      data=dict(nrow=1, ncol=122,
                                row_names=None,
                                col_names=evoked.ch_names, data=np.ones(122)),
                      explained_var=0.5)

    plot_projs_topomap([proj], info=evoked.info, **fast_test)
    plot_projs_topomap([proj], layout=layout, **fast_test)
    pytest.raises(RuntimeError, plot_projs_topomap, [proj], **fast_test)


run_tests_if_main()
