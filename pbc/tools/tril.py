import numpy
import pyscf.lib

def tril_index(ki,kj):
    assert (numpy.array([ki<=kj])).all()
    #return (ki*(ki+1))/2 + kj
    return (kj*(kj+1))/2 + ki

#
# TODO: fairly messy and slow, needs some speed-up too!
#
def unpack_tril(in_array,nkpts,kp,kq,kr,ks):
    # We are only dealing with the case that one of kp,kq,kr is a list
    #
    if in_array.shape[0] == nkpts:
        return in_array[kp,kq,kr].copy()
    nints = sum([isinstance(x,int) for x in kp,kq,kr])
    assert(nints>=2)

    kp,kq,kr,ks = [[x] if isinstance(x,int) else x for x in kp,kq,kr,ks ]
    kp,kq,kr,ks = [numpy.array(x) for x in kp,kq,kr,ks]
    indices = numpy.array(pyscf.lib.cartesian_prod((kp,kq,kr)))

    # If they aren't lower triangular, we permute them indices
    #
    not_tril = numpy.array([x[0]>x[1] for x in indices])
    if sum(not_tril) == 0:
        indices = [tril_index(indices[:,0],indices[:,1]),indices[:,2]]
        tmp = in_array[indices].copy()
        if nints == 3:
            tmp = tmp.reshape(in_array.shape[2:7])
        return tmp
    indices[not_tril] = indices[not_tril][:,[1,0,2]]
    indices[:,2][not_tril] = ks[not_tril]
    #
    indices = [tril_index(indices[:,0],indices[:,1]),indices[:,2]]
    #
    tmp = in_array[indices].copy()
    tmp[not_tril] = tmp[not_tril].transpose(0,2,1,4,3)
    if nints == 3:
        tmp = tmp.reshape(in_array.shape[2:7])
    return tmp
