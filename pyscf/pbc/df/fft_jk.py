#!/usr/bin/env python
#
# Author: Qiming Sun <osirpt.sun@gmail.com>
#

'''
JK with discrete Fourier transformation
'''

import numpy as np
from pyscf import lib
from pyscf.pbc import tools
from pyscf.pbc.dft import numint
from pyscf.pbc.df.df_jk import _format_dms, _format_kpts_band, _format_jks
from pyscf.pbc.lib.kpt_misc import is_zero, gamma_point


def get_j_kpts(mydf, dm_kpts, hermi=1, kpts=np.zeros((1,3)), kpts_band=None):
    '''Get the Coulomb (J) AO matrix at sampled k-points.

    Args:
        dm_kpts : (nkpts, nao, nao) ndarray or a list of (nkpts,nao,nao) ndarray
            Density matrix at each k-point.  If a list of k-point DMs, eg,
            UHF alpha and beta DM, the alpha and beta DMs are contracted
            separately.
        kpts : (nkpts, 3) ndarray

    Kwargs:
        kpts_band : (3,) ndarray or (*,3) ndarray
            A list of arbitrary "band" k-points at which to evalute the matrix.

    Returns:
        vj : (nkpts, nao, nao) ndarray
        or list of vj if the input dm_kpts is a list of DMs
    '''
    cell = mydf.cell
    gs = mydf.gs

    dm_kpts = lib.asarray(dm_kpts, order='C')
    dms = _format_dms(dm_kpts, kpts)
    nset, nkpts, nao = dms.shape[:3]

    coulG = tools.get_coulG(cell, gs=gs)
    ngs = len(coulG)

    vR = rhoR = np.zeros((nset,ngs))
    for k, aoR in mydf.aoR_loop(gs, kpts):
        for i in range(nset):
            rhoR[i] += numint.eval_rho(cell, aoR, dms[i,k])
    for i in range(nset):
        rhoR[i] *= 1./nkpts
        rhoG = tools.fft(rhoR[i], gs)
        vG = coulG * rhoG
        vR[i] = tools.ifft(vG, gs).real

    kpts_band, input_band = _format_kpts_band(kpts_band, kpts), kpts_band
    nband = len(kpts_band)
    weight = cell.vol / ngs
    if gamma_point(kpts_band):
        vj_kpts = np.empty((nset,nband,nao,nao))
    else:
        vj_kpts = np.empty((nset,nband,nao,nao), dtype=np.complex128)
    for k, aoR in mydf.aoR_loop(gs, kpts_band):
        for i in range(nset):
            vj_kpts[i,k] = weight * lib.dot(aoR.T.conj()*vR[i], aoR)

    return _format_jks(vj_kpts, dm_kpts, input_band, kpts)

def get_k_kpts(mydf, dm_kpts, hermi=1, kpts=np.zeros((1,3)), kpts_band=None,
               exxdiv=None):
    '''Get the Coulomb (J) and exchange (K) AO matrices at sampled k-points.

    Args:
        dm_kpts : (nkpts, nao, nao) ndarray
            Density matrix at each k-point
        kpts : (nkpts, 3) ndarray

    Kwargs:
        kpts_band : (3,) ndarray or (*,3) ndarray
            A list of arbitrary "band" k-points at which to evalute the matrix.

    Returns:
        vj : (nkpts, nao, nao) ndarray
        vk : (nkpts, nao, nao) ndarray
        or list of vj and vk if the input dm_kpts is a list of DMs
    '''
    cell = mydf.cell
    gs = mydf.gs
    coords = cell.gen_uniform_grids(gs)
    ngs = coords.shape[0]

    if hasattr(dm_kpts, 'mo_coeff'):
        mo_coeff = dm_kpts.mo_coeff
        mo_occ   = dm_kpts.mo_occ
    else:
        mo_coeff = None

    kpts = np.asarray(kpts)
    dm_kpts = lib.asarray(dm_kpts, order='C')
    dms = _format_dms(dm_kpts, kpts)
    nset, nkpts, nao = dms.shape[:3]

    weight = 1./nkpts * (cell.vol/ngs)

    kpts_band, input_band = _format_kpts_band(kpts_band, kpts), kpts_band
    nband = len(kpts_band)

    if gamma_point(kpts_band) and gamma_point(kpts):
        vk_kpts = np.zeros((nset,nband,nao,nao), dtype=dms.dtype)
    else:
        vk_kpts = np.zeros((nset,nband,nao,nao), dtype=np.complex128)

    ao2_kpts = mydf._numint.eval_ao(cell, coords, kpts, non0tab=mydf.non0tab)
    ao2_kpts = [np.asarray(ao.T, order='C') for ao in ao2_kpts]
    if input_band is None:
        ao1_kpts = ao2_kpts
    else:
        ao1_kpts = mydf._numint.eval_ao(cell, coords, kpts_band, non0tab=mydf.non0tab)
        ao1_kpts = [np.asarray(ao.T, order='C') for ao in ao1_kpts]
    if mo_coeff is not None and nset == 1:
        mo_coeff = [mo_coeff[k][:,occ>0] * np.sqrt(occ[occ>0])
                    for k, occ in enumerate(mo_occ)]
        ao2_kpts = [np.dot(mo_coeff[k].T, ao) for k, ao in enumerate(ao2_kpts)]
        naoj = ao2_kpts[0].shape[0]
    else:
        naoj = nao

    max_memory = mydf.max_memory - lib.current_memory()[0]
    blksize = int(max(max_memory*1e6/16/2/ngs/nao, 1))
    ao1_dtype = np.result_type(*ao1_kpts)
    ao2_dtype = np.result_type(*ao2_kpts)
    buf = np.empty((blksize,naoj,ngs), dtype=np.result_type(ao1_dtype, ao2_dtype))
    vR_dm = np.empty((nset,nao,ngs), dtype=vk_kpts.dtype)
    ao_dms = np.empty((nset,naoj,ngs), dtype=np.result_type(dms, ao2_dtype))

    for k2, ao2T in enumerate(ao2_kpts):
        kpt2 = kpts[k2]
        if mo_coeff is None or nset > 1:
            for i in range(nset):
                lib.dot(dms[i,k2], ao2T.conj(), c=ao_dms[i])
        else:
            ao_dms = [ao2T.conj()]

        for k1, ao1T in enumerate(ao1_kpts):
            kpt1 = kpts_band[k1]
            mydf.exxdiv = exxdiv
            coulG = tools.get_coulG(cell, kpt2-kpt1, True, mydf, gs)
            if is_zero(kpt1-kpt2):
                expmikr = np.array(1.)
            else:
                expmikr = np.exp(-1j * np.dot(coords, kpt2-kpt1))

            for p0, p1 in lib.prange(0, nao, blksize):
                rho1 = np.einsum('ig,jg->ijg', ao1T[p0:p1].conj()*expmikr,
                                 ao2T, out=buf[:p1-p0])
                vG = tools.fft(rho1.reshape(-1,ngs), gs)
                vG *= coulG
                vR = tools.ifft(vG, gs).reshape(p1-p0,naoj,ngs)
                vG = None
                if vR_dm.dtype == np.double:
                    vR = vR.real
                for i in range(nset):
                    np.einsum('ijg,jg->ig', vR, ao_dms[i], out=vR_dm[i,p0:p1])
                vR = None
            vR_dm *= expmikr.conj()

            for i in range(nset):
                vk_kpts[i,k1] += weight * lib.dot(vR_dm[i], ao1T.T)

    return _format_jks(vk_kpts, dm_kpts, input_band, kpts)


def get_jk(mydf, dm, hermi=1, kpt=np.zeros(3), kpt_band=None,
           with_j=True, with_k=True, exxdiv=None):
    '''Get the Coulomb (J) and exchange (K) AO matrices for the given density matrix.

    Args:
        dm : ndarray or list of ndarrays
            A density matrix or a list of density matrices

    Kwargs:
        hermi : int
            Whether J, K matrix is hermitian
            | 0 : no hermitian or symmetric
            | 1 : hermitian
            | 2 : anti-hermitian
        kpt : (3,) ndarray
            The "inner" dummy k-point at which the DM was evaluated (or
            sampled).
        kpt_band : (3,) ndarray
            The "outer" primary k-point at which J and K are evaluated.

    Returns:
        The function returns one J and one K matrix, corresponding to the input
        density matrix (both order and shape).
    '''
    dm = np.asarray(dm, order='C')
    vj = vk = None
    if with_j:
        vj = get_j(mydf, dm, hermi, kpt, kpt_band)
    if with_k:
        vk = get_k(mydf, dm, hermi, kpt, kpt_band, exxdiv)
    return vj, vk

def get_j(mydf, dm, hermi=1, kpt=np.zeros(3), kpt_band=None):
    '''Get the Coulomb (J) AO matrix for the given density matrix.

    Args:
        dm : ndarray or list of ndarrays
            A density matrix or a list of density matrices

    Kwargs:
        hermi : int
            Whether J, K matrix is hermitian
            | 0 : no hermitian or symmetric
            | 1 : hermitian
            | 2 : anti-hermitian
        kpt : (3,) ndarray
            The "inner" dummy k-point at which the DM was evaluated (or
            sampled).
        kpt_band : (3,) ndarray
            The "outer" primary k-point at which J and K are evaluated.

    Returns:
        The function returns one J matrix, corresponding to the input
        density matrix (both order and shape).
    '''
    dm = np.asarray(dm, order='C')
    nao = dm.shape[-1]
    dm_kpts = dm.reshape(-1,1,nao,nao)
    vj_kpts = get_j_kpts(mydf, dm_kpts, hermi, kpt.reshape(1,3), kpt_band)
    return vj_kpts[...,0,:,:]

def get_k(mydf, dm, hermi=1, kpt=np.zeros(3), kpt_band=None, exxdiv=None):
    '''Get the Coulomb (J) and exchange (K) AO matrices for the given density matrix.

    Args:
        dm : ndarray or list of ndarrays
            A density matrix or a list of density matrices

    Kwargs:
        hermi : int
            Whether J, K matrix is hermitian
            | 0 : no hermitian or symmetric
            | 1 : hermitian
            | 2 : anti-hermitian
        kpt : (3,) ndarray
            The "inner" dummy k-point at which the DM was evaluated (or
            sampled).
        kpt_band : (3,) ndarray
            The "outer" primary k-point at which J and K are evaluated.

    Returns:
        The function returns one J and one K matrix, corresponding to the input
        density matrix (both order and shape).
    '''
    dm = np.asarray(dm, order='C')
    nao = dm.shape[-1]
    dm_kpts = dm.reshape(-1,1,nao,nao)
    vk_kpts = get_k_kpts(mydf, dm_kpts, hermi, kpt.reshape(1,3), kpt_band, exxdiv)
    return vk_kpts[...,0,:,:]

