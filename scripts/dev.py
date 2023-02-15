import os

import pyart
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.ndimage import median_filter, uniform_filter
from scipy.signal import savgol_filter

from radproc.aliases import zh, zdr, rhohv, mli
from radproc.preprocessing import RadarDataScaler
from radproc.ml import ind, ml_limits_raw, ml_limits, find


FLTRD_SUFFIX = '_filtered'


def plot_pseudo_rhi(radar, what='reflectivity_horizontal', direction=270, **kws):
    fig, ax = plt.subplots()
    xsect = pyart.util.cross_section_ppi(radar, [direction])
    display = pyart.graph.RadarDisplay(xsect)
    display.plot(what, 0, ax=ax, **kws)
    ax.set_ylim(bottom=0, top=11)
    ax.set_xlim(left=0, right=150)
    return ax


def plot_ppi(radar, sweep=0, what='reflectivity_horizontal', r_km=120, **kws):
    fig, ax = plt.subplots()
    ppi = pyart.graph.RadarDisplay(radar)
    ppi.plot(what, sweep, ax=ax, **kws)
    ax.axis('equal')
    ax.set_xlim(-r_km, r_km)
    ax.set_ylim(-r_km, r_km)
    return ax


def plot_edge(radar, sweep, edge, ax, color='red'):
    x = radar.get_gate_x_y_z(sweep)[0][edge.index.values, edge.gate]
    y = radar.get_gate_x_y_z(sweep)[1][edge.index.values, edge.gate]
    ax.scatter(x/1000, y/1000, marker=',', color=color, edgecolors='none', s=2)


def read_h5(filename, exclude_datasets=['dataset13'], **kws):
    """pyart read_odim_h5 wrapper"""
    try:
        return pyart.aux_io.read_odim_h5(filename,
                                         exclude_datasets=exclude_datasets,
                                         **kws)
    except ValueError:
        exclude_datasets=['dataset7', 'dataset8', 'dataset9']
        return pyart.aux_io.read_odim_h5(filename,
                                         exclude_datasets=exclude_datasets,
                                         **kws)


def scale_field(radar, field, field_type=None, **kws):
    if field_type is None:
        field_type=field
    copy = radar.fields[field]['data'].copy() # to be scaled
    scaler = RadarDataScaler(field_type, **kws)
    scaled = scaler.fit_transform(copy)
    return scaled


def ml_indicator(radar):
    zh_scaled = scale_field(radar, zh)
    zdr_scaled = scale_field(radar, zdr+FLTRD_SUFFIX, field_type=zdr)
    rho = radar.fields[rhohv+FLTRD_SUFFIX]['data']
    return ind(zdr_scaled, zh_scaled, rho)


def add_ml_indicator(radar):
    mlifield = radar.fields[zh].copy()
    mlifield['data'] = ml_indicator(radar)
    mlifield['long_name'] = 'Melting layer indicator'
    mlifield['coordinates'] = radar.fields[zdr]['coordinates']
    radar.add_field(mli, mlifield, replace_existing=True)


def field_filter(field_data, filterfun=median_filter, **kws):
    filtered = filterfun(field_data, **kws)
    return np.ma.array(filtered, mask=field_data.mask)


def filter_field(radar, fieldname, **kws):
    sweeps = radar.sweep_number['data']
    filtered = np.concatenate([field_filter(radar.get_field(n, fieldname), **kws) for n in sweeps])
    filtered = np.ma.array(filtered, mask=radar.fields[fieldname]['data'].mask)
    if fieldname[-len(FLTRD_SUFFIX):] == FLTRD_SUFFIX:
        fieldname_out = fieldname
    else:
        fieldname_out = fieldname+FLTRD_SUFFIX
    radar.add_field_like(fieldname, fieldname_out, filtered, replace_existing=True)


def ppi_altitude(radar, sweep):
    """1D altitude vector along ray from PPI"""
    return radar.get_gate_lat_lon_alt(sweep)[2][1]


def get_field_df(radar, sweep, fieldname):
    """radar field as DataFrame"""
    field = radar.get_field(sweep, fieldname)
    return pd.DataFrame(field.T, index=ppi_altitude(radar, sweep))


def edge_gates(edge, height):
    gates = edge.apply(lambda h: find(height, h))
    gates.name = 'gate'
    return pd.concat([edge, gates], axis=1)


if __name__ == '__main__':
    sweep = 2
    plt.close('all')
    datadir = os.path.expanduser('~/data/pvol/')
    f_nomelt1 = os.path.join(datadir, '202302051845_fivih_PVOL.h5')
    # melting at 1-2km
    f_melt1 = os.path.join(datadir, '202206030010_fivih_PVOL.h5')
    r_nomelt1 = read_h5(f_nomelt1)
    r_melt1 = read_h5(f_melt1)
    #ax0 = plot_pseudo_rhi(r_melt1, what='cross_correlation_ratio', direction=90)
    axzh = plot_ppi(r_melt1, sweep=sweep, what=zh, title_flag=False)
    axrho = plot_ppi(r_melt1, vmin=0.86, vmax=1, sweep=sweep, what=rhohv, title_flag=False)
    axzdr = plot_ppi(r_melt1, sweep=sweep, what=zdr, title_flag=False)
    filter_field(r_melt1, zdr, filterfun=median_filter, size=10, mode='wrap')
    filter_field(r_melt1, rhohv, filterfun=median_filter, size=10, mode='wrap')
    axzdrf = plot_ppi(r_melt1, sweep=sweep, what=zdr+FLTRD_SUFFIX, title_flag=False)
    axrhof = plot_ppi(r_melt1, vmin=0.86, vmax=1, sweep=sweep, what=rhohv+FLTRD_SUFFIX, title_flag=False)
    add_ml_indicator(r_melt1)
    ax2 = plot_ppi(r_melt1, vmin=0, vmax=10, sweep=sweep, what=mli, title_flag=False)
    ax3 = plot_pseudo_rhi(r_melt1, vmin=0, vmax=10, what=mli)
    filter_field(r_melt1, mli, filterfun=uniform_filter, size=(30,1), mode='wrap')
    filter_field(r_melt1, mli, filterfun=savgol_filter, window_length=60, polyorder=3, axis=1)
    axfr = plot_ppi(r_melt1, vmin=0, vmax=10, sweep=sweep, what=mli+FLTRD_SUFFIX, title_flag=False)
    axf = plot_ppi(r_melt1, vmin=0, vmax=10, sweep=sweep, what=mli+FLTRD_SUFFIX, title_flag=False)

    mlidf = get_field_df(r_melt1, sweep, mli+FLTRD_SUFFIX)
    rhodf = get_field_df(r_melt1, sweep, rhohv+FLTRD_SUFFIX)
    botr, topr = ml_limits_raw(mlidf)
    bot, top = ml_limits(mlidf, rhodf)
    h = ppi_altitude(r_melt1, sweep)
    bot = edge_gates(bot, h)
    top = edge_gates(top, h)
    plot_edge(r_melt1, sweep, botr, axfr, color='red')
    plot_edge(r_melt1, sweep, topr, axfr, color='black')
    plot_edge(r_melt1, sweep, bot, axf, color='red')
    plot_edge(r_melt1, sweep, top, axf, color='black')
