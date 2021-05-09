# Copyright 2020 - 2021 MONAI Consortium
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import math
from abc import ABC, abstractmethod
from functools import partial
from typing import Any, Union

import torch

from monai.metrics.utils import do_metric_reduction
from monai.utils import MetricReduction


class RegressionMetric(ABC):
    def __init__(self, reduction: Union[MetricReduction, str] = MetricReduction.MEAN) -> None:
        super().__init__()
        self.reduction = reduction

    def _reduce(self, f: torch.Tensor):
        return do_metric_reduction(f, self.reduction)

    def _check_shape(self, y_pred: torch.Tensor, y: torch.Tensor) -> None:
        if y_pred.shape != y.shape:
            raise ValueError(
                "y_pred and y shapes dont match, received y_pred: [{}] and y: [{}]".format(y_pred.shape, y.shape)
            )

        # also check if there is atleast one non-batch dimension i.e. num_dims >= 2
        if len(y_pred.shape) < 2:
            raise ValueError("either channel or spatial dimensions required, found only batch dimension")

    @abstractmethod
    def _compute_metric(self, y_pred: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
        raise NotImplementedError(f"Subclass {self.__class__.__name__} must implement this method.")

    def __call__(self, y_pred: torch.Tensor, y: torch.Tensor):
        self._check_shape(y_pred, y)
        out = self._compute_metric(y_pred, y)
        y, not_nans = self._reduce(out)
        return y, not_nans


class MSEMetric(RegressionMetric):
    r"""Compute Mean Squared Error between two tensors using function:

    .. math::
        \operatorname {MSE}\left(Y, \hat{Y}\right) =\frac {1}{n}\sum _{i=1}^{n}\left(y_i-\hat{y_i} \right)^{2}.

    More info: https://en.wikipedia.org/wiki/Mean_squared_error

    Input `y_pred` (BCHW[D] where C is number of channels) is compared with ground truth `y` (BCHW[D]).
    Both `y_pred` and `y` are expected to be real-valued, where `y_pred` is output from a regression model.

    Args:
        reduction: {``"none"``, ``"mean"``, ``"sum"``, ``"mean_batch"``, ``"sum_batch"``,
            ``"mean_channel"``, ``"sum_channel"``}
            Define the mode to reduce computation result of 1 batch data. Defaults to ``"mean"``.

    """

    def __init__(self, reduction: Union[MetricReduction, str] = MetricReduction.MEAN) -> None:
        super().__init__(reduction=reduction)
        self.sq_func = partial(torch.pow, exponent=2.0)

    def _compute_metric(self, y_pred: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
        y_pred = y_pred.float()
        y = y.float()

        mse_out = compute_mean_error_metrics(y_pred, y, func=self.sq_func)
        return mse_out


class MAEMetric(RegressionMetric):
    r"""Compute Mean Absolute Error between two tensors using function:

    .. math::
        \operatorname {MAE}\left(Y, \hat{Y}\right) =\frac {1}{n}\sum _{i=1}^{n}\left|y_i-\hat{y_i}\right|.

    More info: https://en.wikipedia.org/wiki/Mean_absolute_error

    Input `y_pred` (BCHW[D] where C is number of channels) is compared with ground truth `y` (BCHW[D]).
    Both `y_pred` and `y` are expected to be real-valued, where `y_pred` is output from a regression model.

    Args:
        reduction: {``"none"``, ``"mean"``, ``"sum"``, ``"mean_batch"``, ``"sum_batch"``,
            ``"mean_channel"``, ``"sum_channel"``}
            Define the mode to reduce computation result of 1 batch data. Defaults to ``"mean"``.

    """

    def __init__(self, reduction: Union[MetricReduction, str] = MetricReduction.MEAN) -> None:
        super().__init__(reduction=reduction)
        self.abs_func = torch.abs

    def _compute_metric(self, y_pred: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
        y_pred = y_pred.float()
        y = y.float()

        mae_out = compute_mean_error_metrics(y_pred, y, func=self.abs_func)
        return mae_out



class RMSEMetric(RegressionMetric):
    r"""Compute Root Mean Squared Error between two tensors using function:

    .. math::
        \operatorname {RMSE}\left(Y, \hat{Y}\right) ={ \sqrt{ \frac {1}{n}\sum _{i=1}^{n}\left(y_i-\hat{y_i}\right)^2 } } \
        = \sqrt {\operatorname{MSE}\left(Y, \hat{Y}\right)}.

    More info: https://en.wikipedia.org/wiki/Root-mean-square_deviation

    Input `y_pred` (BCHW[D] where C is number of channels) is compared with ground truth `y` (BCHW[D]).
    Both `y_pred` and `y` are expected to be real-valued, where `y_pred` is output from a regression model.

    Args:
        reduction: {``"none"``, ``"mean"``, ``"sum"``, ``"mean_batch"``, ``"sum_batch"``,
            ``"mean_channel"``, ``"sum_channel"``}
            Define the mode to reduce computation result of 1 batch data. Defaults to ``"mean"``.

    """

    def __init__(self, reduction: Union[MetricReduction, str] = MetricReduction.MEAN) -> None:
        super().__init__(reduction=reduction)
        self.sq_func = partial(torch.pow, exponent=2.0)

    def _compute_metric(self, y_pred: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
        y_pred = y_pred.float()
        y = y.float()

        mse_out = compute_mean_error_metrics(y_pred, y, func=self.sq_func)
        rmse_out = torch.sqrt(mse_out)
        return rmse_out



class PSNRMetric(RegressionMetric):
    r"""Compute Peak Signal To Noise Ratio between two tensors using function:

    .. math::
        \operatorname{PSNR}\left(Y, \hat{Y}\right) = 20 \cdot \log_{10} \left({\mathit{MAX}}_Y\right) \
        -10 \cdot \log_{10}\left(\operatorname{MSE\left(Y, \hat{Y}\right)}\right)

    More info: https://en.wikipedia.org/wiki/Peak_signal-to-noise_ratio

    Help taken from:
    https://github.com/tensorflow/tensorflow/blob/master/tensorflow/python/ops/image_ops_impl.py line 4139

    Input `y_pred` (BCHW[D] where C is number of channels) is compared with ground truth `y` (BCHW[D]).
    Both `y_pred` and `y` are expected to be real-valued, where `y_pred` is output from a regression model.

    Args:
        max_val: The dynamic range of the images/volumes (i.e., the difference between the
            maximum and the minimum allowed values e.g. 255 for a uint8 image).
        reduction: {``"none"``, ``"mean"``, ``"sum"``, ``"mean_batch"``, ``"sum_batch"``,
            ``"mean_channel"``, ``"sum_channel"``}
            Define the mode to reduce computation result of 1 batch data. Defaults to ``"mean"``.

    """

    def __init__(
        self, max_val: Union[int, float], reduction: Union[MetricReduction, str] = MetricReduction.MEAN
    ) -> None:
        super().__init__(reduction=reduction)
        self.max_val = max_val
        self.sq_func = partial(torch.pow, exponent=2.0)

    def _compute_metric(self, y_pred: torch.Tensor, y: torch.Tensor) -> Any:
        y_pred = y_pred.float()
        y = y.float()

        mse_out = compute_mean_error_metrics(y_pred, y, func=self.sq_func)
        psnr_val = 20 * math.log10(self.max_val) - 10 * torch.log10(mse_out)
        return psnr_val



def compute_mean_error_metrics(y_pred: torch.Tensor, y: torch.Tensor, func) -> torch.Tensor:
    # reducing in only channel + spatial dimensions (not batch)
    # reducion of batch handled inside __call__() using do_metric_reduction() in respective calling class
    flt = partial(torch.flatten, start_dim=1)
    error_metric = torch.mean(flt(func(y - y_pred)), dim=-1, keepdim=True)

    return error_metric
