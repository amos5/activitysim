import copy
import os

import orca
import pandas as pd
import yaml

from activitysim import activitysim as asim
from activitysim import skim as askim

"""
Mode choice is run for all tours to determine the transportation mode that
will be used for the tour
"""


@orca.injectable()
def mode_choice_settings(configs_dir):
    with open(os.path.join(configs_dir, "configs", "mode_choice.yaml")) as f:
        return yaml.load(f)


# FIXME move into activitysim as a utility function
def evaluate_expression_list(expressions, locals_d):
    """
    Evaluate a list of expressions - each one can depend on the one before it

    Parameters
    ----------
    expressions : Series
        indexes are names and values are expressions
    locals_d : dict
        will be passed directly to eval

    Returns
    -------
    expressions : Series
        index is the same as above, but values are now confirmed to be floats
    """
    d = {}
    # this could be a simple expression except that the dictionary
    # is accumulating expressions - i.e. they're not all independent
    # and must be evaluated in order
    for k, v in expressions.iteritems():
        # make sure it can be converted to a float
        d[k] = float(eval(str(v), copy.copy(d), locals_d))
    return pd.Series(d)


@orca.injectable()
def mode_choice_coefficients(mode_choice_settings):
    # coefficients comes as a list of dicts and needs to be tuples
    coeffs = [x.items()[0] for x in mode_choice_settings['COEFFICIENTS']]
    expressions = pd.Series(zip(*coeffs)[1], index=zip(*coeffs)[0])
    constants = mode_choice_settings['CONSTANTS']
    return evaluate_expression_list(expressions, locals_d=constants)


@orca.injectable()
def mode_choice_spec(configs_dir, mode_choice_coefficients):
    f = os.path.join(configs_dir, 'configs', "mode_choice_work.csv")
    df = asim.read_model_spec(f)
    df['work'] = evaluate_expression_list(df['work'],
                                          mode_choice_coefficients.to_dict())
    return df.set_index('Alternative', append=True)


def get_segment_and_unstack(spec, segment):
    return spec[segment].unstack().fillna(0)


@orca.step()
def mode_choice_simulate(tours_merged,
                         mode_choice_spec,
                         mode_choice_settings,
                         skims):

    tours = tours_merged.to_frame()
    tours = tours[tours.tour_type == "work"]

    mode_choice_spec = mode_choice_spec.head(33)

    # the skims will be available under the name "skims" for any @ expressions
    in_skims = askim.Skims3D(skims.set_keys("TAZ", "workplace_taz"),
                             "in_period", -1)
    out_skims = askim.Skims3D(skims.set_keys("workplace_taz", "TAZ"),
                              "out_period", -1)
    locals_d = {
        "in_skims": in_skims,
        "out_skims": out_skims
    }
    locals_d.update(mode_choice_settings['CONSTANTS'])

    # FIXME lots of other segments here - for now running the mode choice for
    # FIXME work on all kinds of tour types
    # FIXME note that in particular the spec above only has work tours in it

    choices, _ = asim.simple_simulate(tours,
                                      get_segment_and_unstack(mode_choice_spec,
                                                              'work'),
                                      skims=[in_skims, out_skims],
                                      locals_d=locals_d)

    print "Choices:\n", choices.value_counts()
    orca.add_column("tours", "mode", choices)
