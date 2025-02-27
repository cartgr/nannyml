#  Author:   Niels Nuyttens  <niels@nannyml.com>
#
#  License: Apache Software License 2.0

"""Contains the results of the realized performance calculation and provides plotting functionality."""
from __future__ import annotations

import copy
from typing import Dict, List, Optional, Union, cast

import pandas as pd
import plotly.graph_objects as go

from nannyml._typing import Key, ProblemType
from nannyml.base import Abstract1DResult
from nannyml.exceptions import InvalidArgumentsException
from nannyml.performance_calculation import SUPPORTED_METRIC_FILTER_VALUES
from nannyml.performance_calculation.metrics.base import Metric
from nannyml.plots.blueprints.comparisons import ResultCompareMixin
from nannyml.plots.blueprints.metrics import plot_metrics
from nannyml.usage_logging import UsageEvent, log_usage


class Result(Abstract1DResult[Metric], ResultCompareMixin):
    """Contains the results of the realized performance calculation and provides plotting functionality."""

    metrics: List[Metric]

    def __init__(
        self,
        results_data: pd.DataFrame,
        problem_type: ProblemType,
        y_pred: str,
        y_pred_proba: Optional[Union[str, Dict[str, str]]],
        y_true: str,
        metrics: List[Metric],
        timestamp_column_name: Optional[str] = None,
        reference_data: Optional[pd.DataFrame] = None,
        analysis_data: Optional[pd.DataFrame] = None,
    ):
        """Creates a new Result instance."""
        super().__init__(results_data, metrics)

        self.problem_type = problem_type

        self.y_true = y_true
        self.y_pred_proba = y_pred_proba
        self.y_pred = y_pred
        self.timestamp_column_name = timestamp_column_name

        self.reference_data = reference_data
        self.analysis_data = analysis_data

    def keys(self) -> List[Key]:
        return [
            Key(
                properties=(component[1],),
                display_names=(
                    f'estimated {component[0]}',
                    component[0],
                ),
            )
            for metric in self.metrics
            for component in cast(Metric, metric).components
        ]

    @log_usage(UsageEvent.PERFORMANCE_PLOT, metadata_from_kwargs=['kind'])
    def plot(
        self,
        kind: str = 'performance',
        *args,
        **kwargs,
    ) -> go.Figure:
        """Render realized performance metrics.

            The following kinds of plots are available:

        - ``performance``
                a step plot showing the realized performance metric per :class:`~nannyml.chunk.Chunk` for
                a given metric.

        Parameters
        ----------
        kind: str, default='performance'
            The kind of plot to render. Only the 'performance' plot is currently available.

        Returns
        -------
        fig: :class:`plotly.graph_objs._figure.Figure`
            A :class:`~plotly.graph_objs._figure.Figure` object containing the requested drift plot.

            Can be saved to disk using the :meth:`~plotly.graph_objs._figure.Figure.write_image` method
            or shown rendered on screen using the :meth:`~plotly.graph_objs._figure.Figure.show` method.

        Examples
        --------
        >>> import nannyml as nml
        >>>
        >>> reference_df, analysis_df, target_df = nml.load_synthetic_binary_classification_dataset()
        >>>
        >>> calc = nml.PerformanceCalculator(y_true='work_home_actual', y_pred='y_pred', y_pred_proba='y_pred_proba',
        >>>                                  timestamp_column_name='timestamp', metrics=['f1', 'roc_auc'])
        >>>
        >>> calc.fit(reference_df)
        >>>
        >>> results = calc.calculate(analysis_df.merge(target_df, on='identifier'))
        >>> print(results.data)
                     key  start_index  ...  roc_auc_upper_threshold roc_auc_alert
        0       [0:4999]            0  ...                  0.97866         False
        1    [5000:9999]         5000  ...                  0.97866         False
        2  [10000:14999]        10000  ...                  0.97866         False
        3  [15000:19999]        15000  ...                  0.97866         False
        4  [20000:24999]        20000  ...                  0.97866         False
        5  [25000:29999]        25000  ...                  0.97866          True
        6  [30000:34999]        30000  ...                  0.97866          True
        7  [35000:39999]        35000  ...                  0.97866          True
        8  [40000:44999]        40000  ...                  0.97866          True
        9  [45000:49999]        45000  ...                  0.97866          True
        >>> for metric in calc.metrics:
        >>>     results.plot(metric=metric, plot_reference=True).show()
        """
        if kind == 'performance':
            return plot_metrics(
                result=self,
                title='Realized performance',
                subplot_title_format='Realized <b>{display_names[1]}</b>',
                subplot_y_axis_title_format='{display_names[1]}',
            )
        else:
            raise InvalidArgumentsException(f"unknown plot kind '{kind}'. " f"Please provide on of: ['performance'].")

    def _filter(self, period: str, metrics: Optional[List[str]] = None, *args, **kwargs) -> Result:
        """Filter the results based on the specified period and metrics."""
        if metrics is None:
            filtered_metrics = self.metrics
        else:
            filtered_metrics = []
            for name in metrics:
                if name not in SUPPORTED_METRIC_FILTER_VALUES:
                    raise InvalidArgumentsException(f"invalid metric '{name}'")

                m = self._get_metric_by_name(name)

                if m:
                    filtered_metrics = filtered_metrics + [m]
                else:
                    raise InvalidArgumentsException(f"no '{name}' in result, did you calculate it?")

        metric_column_names = [name for metric in filtered_metrics for name in metric.column_names]

        data = pd.concat([self.data.loc[:, (['chunk'])], self.data.loc[:, (metric_column_names,)]], axis=1)
        if period != 'all':
            data = data.loc[data.loc[:, ('chunk', 'period')] == period, :]

        data = data.reset_index(drop=True)
        res = copy.deepcopy(self)
        res.data = data
        res.metrics = filtered_metrics

        return res

    def _get_metric_by_name(self, name: str) -> Optional[Metric]:
        for metric in self.metrics:
            # If we match the metric by name, return the metric
            # E.g. matching the name 'confusion_matrix'
            if name == metric.name:
                return metric
            # If we match one of the metric component names
            # E.g. matching the name 'true_positive' with the confusion matrix metric
            elif name in metric.column_names:
                # Only retain the component whose column name was given to filter on
                res = copy.deepcopy(metric)
                res.components = list(filter(lambda c: c[1] == name, metric.components))
                return res
            else:
                continue
        return None
