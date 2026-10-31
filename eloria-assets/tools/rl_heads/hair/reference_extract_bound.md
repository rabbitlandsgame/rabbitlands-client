# Complete hanging hair extraction

`reference_surface.py extract --hair-min-y <world Y>` optionally retains an
approved long ponytail or braid below the default head-centre minus 0.34m crop.
The explicit bound must be finite and 0.1–1.2m below the fitted head centre. With
no argument, extraction and its receipt retain their previous behavior.

The option changes only the lower crop. Colour classification, scalp-connected
component selection, incidental-island removal and original loop paint remain
unchanged. It cannot turn clothing into classified hair. Record the chosen
bound in the owned profile and retain the original extraction for comparison.
The extraction receipt includes the selected bound plus source/fit hashes.
Inspect the complete tip from front, both sides and back before preparing
topology or grooming; a lower bound alone does not certify segmentation.
