#!/usr/bin/env python

# Going by the architecture used in Srivastava's paper, detailed here:
# https://github.com/lisa-lab/pylearn2/blob/master/pylearn2/scripts/papers/dropout/mnist_valid.yaml
# 
# Unsure how to deal with input dropout; we're assuming (in the case of Wang)
# that input dropout is propagated through to be noise on the pre-nonlinearity
# activations. But then, the final noise is going to end up directly damaging
# the predictions, which makes no sense. Probably better just to ignore reason
# in this case and just write the architecture the way it's probably supposed
# to be.

import layers
import holonets
import lasagne.layers
import lasagne.nonlinearities
import lasagne.updates
import theano
import theano
import theano.tensor as T
import urllib2
import imp
import argparse
from collections import OrderedDict

def wangDropoutArchitecture(batch_size=1000, input_dim=784, output_dim=10,
                            DropoutLayer=layers.WangGaussianDropout,
                            n_hidden=100):
    l_in = lasagne.layers.InputLayer((batch_size, input_dim))
    l_drop_in = DropoutLayer(l_in, p=0.2)
    l_hidden_1 = lasagne.layers.DenseLayer(l_drop_in, num_units=n_hidden, 
            nonlinearity=lambda x: x)
    l_drop_1 = DropoutLayer(l_hidden_1, p=0.5, 
            nonlinearity=lasagne.nonlinearities.rectify)
    l_hidden_2 = lasagne.layers.DenseLayer(l_drop_1, num_units=n_hidden,
            nonlinearity=lambda x: x)
    l_drop_2 = DropoutLayer(l_hidden_2, p=0.5, 
            nonlinearity=lasagne.nonlinearities.rectify)
    l_out = lasagne.layers.DenseLayer(l_drop_2, num_units=output_dim,
            nonlinearity=lasagne.nonlinearities.softmax)
    return l_out

def vardropBDropoutArchitecture(batch_size=1000, input_dim=784, output_dim=10,
                            DropoutLayer=layers.VariationalDropoutB,
                            n_hidden=100):
    l_in = lasagne.layers.InputLayer((batch_size, input_dim))
    l_drop_in = DropoutLayer(l_in, p=0.2, adaptive="elementwise")
    l_hidden_1 = lasagne.layers.DenseLayer(l_drop_in, num_units=n_hidden, 
            nonlinearity=lambda x: x)
    l_drop_1 = DropoutLayer(l_hidden_1, p=0.5, 
            nonlinearity=lasagne.nonlinearities.rectify, adaptive="elementwise")
    l_hidden_2 = lasagne.layers.DenseLayer(l_drop_1, num_units=n_hidden,
            nonlinearity=lambda x: x)
    l_drop_2 = DropoutLayer(l_hidden_2, p=0.5, 
            nonlinearity=lasagne.nonlinearities.rectify, adaptive="elementwise")
    l_out = lasagne.layers.DenseLayer(l_drop_2, num_units=output_dim,
            nonlinearity=lasagne.nonlinearities.softmax)
    return l_out

def srivastavaDropoutArchitecture(batch_size=1000, input_dim=784, output_dim=10,
                            DropoutLayer=layers.SrivastavaGaussianDropout,
                            n_hidden=100):
    l_in = lasagne.layers.InputLayer((batch_size, input_dim))
    l_drop_in = DropoutLayer(l_in, p=0.2)
    l_hidden_1 = lasagne.layers.DenseLayer(l_drop_in, num_units=n_hidden, 
            nonlinearity=lasagne.nonlinearities.rectify)
    l_drop_1 = DropoutLayer(l_hidden_1, p=0.5)
    l_hidden_2 = lasagne.layers.DenseLayer(l_drop_1, num_units=n_hidden,
            nonlinearity=lasagne.nonlinearities.rectify)
    l_drop_2 = DropoutLayer(l_hidden_2, p=0.5)
    l_out = lasagne.layers.DenseLayer(l_drop_2, num_units=output_dim,
            nonlinearity=lasagne.nonlinearities.softmax)
    return l_out

def vardropADropoutArchitecture(batch_size=1000, input_dim=784, output_dim=10,
                            DropoutLayer=layers.VariationalDropoutA,
                            n_hidden=100):
    l_in = lasagne.layers.InputLayer((batch_size, input_dim))
    l_drop_in = DropoutLayer(l_in, p=0.2, adaptive="elementwise")
    l_hidden_1 = lasagne.layers.DenseLayer(l_drop_in, num_units=n_hidden, 
            nonlinearity=lasagne.nonlinearities.rectify)
    l_drop_1 = DropoutLayer(l_hidden_1, p=0.5, adaptive="elementwise")
    l_hidden_2 = lasagne.layers.DenseLayer(l_drop_1, num_units=n_hidden,
            nonlinearity=lasagne.nonlinearities.rectify)
    l_drop_2 = DropoutLayer(l_hidden_2, p=0.5, adaptive="elementwise")
    l_out = lasagne.layers.DenseLayer(l_drop_2, num_units=output_dim,
            nonlinearity=lasagne.nonlinearities.softmax)
    return l_out

def make_experiment(l_out, dataset, batch_size=1000, 
        N_train=50000, N_valid=10000, N_test=10000, 
        loss_function=lasagne.objectives.categorical_crossentropy,
        extra_loss=0.0, limit_alpha=False):
    """
    Build a loop for training a model, evaluating loss on training, validation 
    and test.
    """
    expressions = holonets.monitor.Expressions(l_out, dataset, 
            batch_size=batch_size, update_rule=lasagne.updates.adam, 
            loss_function=loss_function, loss_aggregate=T.mean, 
            extra_loss=extra_loss, learning_rate=0.001, momentum=0.1)
    # only add channels for loss and accuracy
    for deterministic,dataset in zip([False, True, True],
                                     ["train", "valid", "test"]):
        expressions.add_channel(**expressions.loss(dataset, deterministic))
        expressions.add_channel(**expressions.accuracy(dataset, deterministic))
    channels = expressions.build_channels()
    if limit_alpha:
        # then add channel to reset all alphas at 1.0
        alphas = [p for p in lasagne.layers.get_all_params(l_out) 
                if p.name == "alpha"]
        alpha_ceiling = theano.function([], alphas, 
                updates=OrderedDict([(a, T.min([a, 1.0])) for a in alphas]))
        channels.append({'dataset': 'train',
                         'eval': lambda x: alpha_ceiling(),
                         'dimensions': ['Alpha']*len(alphas),
                         'names': ['alpha {0}'.format(i) for i in range(len(alphas))]})
    train = holonets.train.Train(channels, 
            n_batches={'train': N_train//batch_size, 
                       'valid':N_valid//batch_size, 
                       'test':N_test//batch_size})
    loop = holonets.run.EpochLoop(train, dimensions=train.dimensions)
    return loop

def earlystopping(loop, delta=0.001, max_N=1000, verbose=False):
    """
    Stops the expriment once the loss stops improving by delta per epoch.
    With a max_N of epochs to avoid infinite experiments.
    """
    prev_loss, loss_diff = 100, 0.9
    N = 0
    while abs(loss_diff) > delta and N < max_N:
        # run one epoch
        results = loop.run(1)
        N += 1
        current_loss = loop.results["valid Loss"][-1][1]
        loss_diff = (prev_loss-current_loss)/prev_loss
        if verbose:
            print N, loss_diff
        prev_loss = current_loss
    return results

def load_data():
    """
    Standardising data loading; all using MNIST in the usual way:
        * train: 50000
        * valid: 10000
        * test: separate 10000
    """
    # is this the laziest way to load mnist?
    mnist = imp.new_module('mnist')
    exec urllib2.urlopen("https://raw.githubusercontent.com/Lasagne/Lasagne"
            "/master/examples/mnist.py").read() in mnist.__dict__
    dataset = mnist.load_dataset()
    return dict(X_train=dataset[0].reshape(-1, 784),
                y_train=dataset[1],
                X_valid=dataset[2].reshape(-1, 784),
                y_valid=dataset[3],
                X_test=dataset[4].reshape(-1, 784),
                y_test=dataset[5])

def get_argparser():
    parser = argparse.ArgumentParser()
    parser.add_argument("output_directory", help="directory to save pickle "
            "files of results")
    parser.add_argument("-v", action='store_true', 
            help="make the experiment more verbose")
    return parser
