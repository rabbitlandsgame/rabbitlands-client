import numpy as np
import pytest
from repair_mossbound_limb_skin import budget


def test_eight_slots_nonnegative_normalized_and_deterministic():
    values=np.array([[.1,.2,.3,.4,.5,.6,.7,.8,.9,1.]])
    answer=budget(values)
    assert np.count_nonzero(answer)==8
    assert np.all(answer>=0) and abs(answer.sum()-1)<1e-15
    assert np.array_equal(answer,budget(values))
    assert np.array_equal(values,np.array([[.1,.2,.3,.4,.5,.6,.7,.8,.9,1.]]))


@pytest.mark.parametrize('values',[[[0.,0.]],[[1.,-.1]],[[float('nan'),1.]]])
def test_invalid_or_empty_support_rejected(values):
    with pytest.raises(ValueError):budget(values)
