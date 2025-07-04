import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import tkinter as tk
from tkinter import ttk
import ttkbootstrap as ttkb

def create_spending_charts(data_manager, parent):
    # Create a new window for the charts
    chart_window = ttkb.Toplevel(parent)
    chart_window.title("Spending Analysis")
    chart_window.geometry("800x600")

    # Create notebook for tabs
    notebook = ttk.Notebook(chart_window)
    notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    # Get spending data
    main_spending, custom_spending = data_manager.get_category_spending()

    # Color palettes (use matplotlib.colormaps for compatibility)
    import matplotlib
    # Get color lists from colormaps
    def get_colors(colormap_name, n):
        cmap = matplotlib.colormaps[colormap_name]
        return [cmap(i / max(n - 1, 1)) for i in range(n)] if n > 0 else None

    main_colors = get_colors('Set2', len([amt for amt in main_spending.values() if amt > 0]))
    custom_colors = get_colors('Pastel1', len([amt for amt in custom_spending.values() if amt > 0]))

    # Create main categories chart
    main_frame = ttk.Frame(notebook)
    notebook.add(main_frame, text="Main Categories")

    # Add summary table for main categories
    summary_frame1 = ttk.Frame(main_frame)
    summary_frame1.pack(fill=tk.X, pady=(5, 0))
    ttk.Label(summary_frame1, text="Main Category Spending Summary", font=("", 10, "bold")).pack()
    for category, amount in main_spending.items():
        ttk.Label(summary_frame1, text=f"{category.title()}: ₹{amount:,.2f}").pack(anchor="w")

    fig1, ax1 = plt.subplots(figsize=(7.5, 5.5), dpi=110)
    main_labels = []
    main_values = []

    for category, amount in main_spending.items():
        if amount > 0:
            main_labels.append(category.title())
            main_values.append(amount)

    if main_values:
        pie_result = ax1.pie(
            main_values, labels=main_labels, autopct='%1.1f%%',
            startangle=90, pctdistance=0.85, colors=main_colors
        )
        # Handle both 2-tuple and 3-tuple returns
        if len(pie_result) == 3:
            wedges, texts, autotexts = pie_result
        else:
            wedges, texts = pie_result
            autotexts = []
        # Draw donut hole
        from matplotlib.patches import Circle
        centre_circle = Circle((0, 0), 0.70, fc='white')
        fig1.gca().add_artist(centre_circle)
        ax1.set_title("Spending by Main Category")
        # Move labels outside
        for text in texts:
            text.set_fontsize(10)
        for autotext in autotexts:
            autotext.set_fontsize(9)
            autotext.set_color('black')
        ax1.legend(wedges, main_labels, title="Categories", loc="center left", bbox_to_anchor=(1, 0.5))
    else:
        ax1.text(0.5, 0.5, "No spending data available", ha='center', va='center', fontsize=12)
        ax1.axis('off')

    canvas1 = FigureCanvasTkAgg(fig1, master=main_frame)
    canvas1.draw()
    canvas1.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    # Create custom categories chart
    custom_frame = ttk.Frame(notebook)
    notebook.add(custom_frame, text="Custom Categories")

    # Add summary table for custom categories
    summary_frame2 = ttk.Frame(custom_frame)
    summary_frame2.pack(fill=tk.X, pady=(5, 0))
    ttk.Label(summary_frame2, text="Custom Category Spending Summary", font=("", 10, "bold")).pack()
    for category, amount in custom_spending.items():
        ttk.Label(summary_frame2, text=f"{category}: ₹{amount:,.2f}").pack(anchor="w")

    # Use tk.Frame for better centering
    chart_center_frame = tk.Frame(custom_frame)
    chart_center_frame.pack(fill=tk.BOTH, expand=True)

    fig2, ax2 = plt.subplots(figsize=(18.92, 10.41), dpi=100)
    custom_labels = []
    custom_values = []

    for category, amount in custom_spending.items():
        if amount > 0:
            custom_labels.append(category)
            custom_values.append(amount)

    if custom_values:
        pie_result = ax2.pie(
            custom_values, labels=custom_labels, autopct='%1.1f%%',
            startangle=90, pctdistance=0.85, colors=custom_colors
        )
        # Handle both 2-tuple and 3-tuple returns
        if len(pie_result) == 3:
            wedges, texts, autotexts = pie_result
        else:
            wedges, texts = pie_result
            autotexts = []
        from matplotlib.patches import Circle
        centre_circle = Circle((0, 0), 0.70, fc='white')
        fig2.gca().add_artist(centre_circle)
        ax2.set_title("Spending by Custom Category")
        for text in texts:
            text.set_fontsize(10)
        for autotext in autotexts:
            autotext.set_fontsize(9)
            autotext.set_color('black')
        ax2.legend(wedges, custom_labels, title="Categories", loc="center left", bbox_to_anchor=(1, 0.5))
    else:
        ax2.text(0.5, 0.5, "No spending data available", ha='center', va='center', fontsize=12)
        ax2.axis('off')

    canvas2 = FigureCanvasTkAgg(fig2, master=chart_center_frame)
    canvas2.draw()
    # Pack with expand and center anchor for true centering
    canvas2.get_tk_widget().pack(expand=True, anchor="center")

    def on_close():
        plt.close('all')
        chart_window.destroy()

    chart_window.protocol("WM_DELETE_WINDOW", on_close)
