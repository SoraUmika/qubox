import numpy as np
import matplotlib.pyplot as plt

def plot_hm(data, x_data, y_data,
            xlabel='X-axis', ylabel='Y-axis',
            title='Heatmap', barlabel='Intensity',
            ax=None, figsize=(8,6)):
    """
    Plots a heatmap of `data` vs `x_data` and `y_data`.

    Parameters
    ----------
    data : 2D array-like
    x_data : 1D array-like (length = number of columns in data)
    y_data : 1D array-like (length = number of rows in data)
    xlabel, ylabel, title, barlabel : str
        Labels and title for the plot.
    ax : matplotlib.axes.Axes, optional
        If provided, plot into this Axes; otherwise create a new figure + Axes.
    figsize : tuple, optional
        Figure size if a new figure is created.

    Returns
    -------
    fig : matplotlib.figure.Figure
    ax : matplotlib.axes.Axes
    heatmap : AxesImage
    """
    matrix = np.array(data)
    x_data = np.array(x_data)
    y_data = np.array(y_data)

    # Dimensional sanity check
    n, m = matrix.shape
    if x_data.shape[0] != m or y_data.shape[0] != n:
        raise ValueError("Matrix must be shape (len(y_data), len(x_data)).")

    # Compute extent
    x_min, x_max = x_data.min(), x_data.max()
    y_min, y_max = y_data.min(), y_data.max()

    # Create fig/ax if needed
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure

    # Plot
    heatmap = ax.imshow(
        matrix,
        extent=[x_min, x_max, y_min, y_max],
        origin='lower',
        aspect='auto'
    )
    # Colorbar
    cbar = fig.colorbar(heatmap, ax=ax, label=barlabel)

    # Labels and title
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)

    return fig, ax, heatmap
