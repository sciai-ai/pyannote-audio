#!/usr/bin/env python
# encoding: utf-8

# The MIT License (MIT)

# Copyright (c) 2018 CNRS

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# AUTHORS
# Hervé BREDIN - http://herve.niderb.fr

from typing import Optional
from pathlib import Path
import numpy as np

import chocolate
from pyannote.pipeline import Pipeline

from pyannote.core import Annotation
from pyannote.core import SlidingWindowFeature

from pyannote.audio.signal import Binarize
from pyannote.audio.features import Precomputed

from pyannote.database import get_annotated
from pyannote.database import get_unique_identifier
from pyannote.metrics.detection import DetectionErrorRate


class SpeechActivityDetection(Pipeline):
    """Speech activity detection pipeline

    Parameters
    ----------
    scores : `Path`
        Path to precomputed scores.
    """

    def __init__(self, scores: Optional[Path] = None):
        super().__init__()

        if scores is None:
            msg = 'Path to precomputed scores must be provided.'
            raise ValueError(msg)

        self.scores = scores
        self.precomputed_ = Precomputed(self.scores)

        # hyper-parameters
        self.onset = chocolate.uniform(0., 1.)
        self.offset = chocolate.uniform(0., 1.)
        self.min_duration_on = chocolate.uniform(0., 2.)
        self.min_duration_off = chocolate.uniform(0., 2.)
        self.pad_onset = chocolate.uniform(-1., 1.)
        self.pad_offset = chocolate.uniform(-1., 1.)

    def instantiate(self):
        """Instantiate pipeline with current set of parameters"""

        self.binarize_ = Binarize(
            onset=self.onset,
            offset=self.offset,
            min_duration_on=self.min_duration_on,
            min_duration_off=self.min_duration_off,
            pad_onset=self.pad_onset,
            pad_offset=self.pad_offset)

    def __call__(self, current_file: dict) -> Annotation:
        """Apply speech activity detection

        Parameters
        ----------
        current_file : `dict`
            File as provided by a pyannote.database protocol.

        Returns
        -------
        speech : `pyannote.core.Annotation`
            Speech regions.
        """

        # extract precomputed scores
        precomputed = self.precomputed_(current_file)

        # if this check has not been done yet, do it once and for all
        if not hasattr(self, "log_scale_"):
            # heuristic to determine whether scores are log-scaled
            if np.nanmean(precomputed.data) < 0:
                self.log_scale_ = True
            else:
                self.log_scale_ = False

        data = np.exp(precomputed.data) if self.log_scale_ \
               else precomputed.data

        # speech vs. non-speech
        speech_prob = SlidingWindowFeature(
            1. - data[:, 0],
            precomputed.sliding_window)
        speech = self.binarize_.apply(speech_prob)
        speech.uri = get_unique_identifier(current_file)
        return speech.to_annotation(generator='string', modality='speech')

    def loss(self, current_file: dict, hypothesis: Annotation) -> float:
        """Compute detection error rate

        Parameters
        ----------
        current_file : `dict`
            File as provided by a pyannote.database protocol.
        hypothesis : `pyannote.core.Annotation`
            Speech regions.

        Returns
        -------
        error : `float`
            Detection error rate
        """

        metric = DetectionErrorRate(collar=0.0, skip_overlap=False)
        reference  = current_file['annotation']
        uem = get_annotated(current_file)
        return metric(reference, hypothesis, uem=uem)
