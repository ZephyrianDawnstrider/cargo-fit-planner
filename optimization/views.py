from django.shortcuts import render
from .forms import UploadForm
from .utils import load_data, convert_weights, calculate_days_remaining, analyze_weight_classes
import pandas as pd

def upload_view(request):
    if request.method == 'POST':
        form = UploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = request.FILES['uploaded_file']
            volume_class = form.cleaned_data['volume_class']
            dcd_upper_limit = form.cleaned_data['dcd_upper_limit']
            include_cost = form.cleaned_data['include_cost']

            # Determine file type
            file_name = uploaded_file.name
            if file_name.endswith('.csv'):
                file_type = 'csv'
            elif file_name.endswith(('.xlsx', '.xls')):
                file_type = 'excel'
            else:
                return render(request, 'optimization/upload.html', {'form': form, 'error': 'Unsupported file type. Please upload a CSV or Excel file.'})

            # Load and process data
            try:
                data = load_data(uploaded_file, file_type)
                data = convert_weights(data)
                data = calculate_days_remaining(data)

                fulfilled_files, unfulfilled_files, best_class = analyze_weight_classes(data, dcd_upper_limit, include_cost)

                # Prepare data for template
                best_packages = []
                total_cost_best_class = 0
                if fulfilled_files:
                    for weight_class, packages in fulfilled_files.items():
                        if weight_class == best_class:
                            for pkg in packages:
                                best_packages.append({
                                    'console_data_html': pkg['Console Data'].to_html(index=False, classes='table table-striped table-bordered'),
                                    'total_weight': pkg['Total Weight'],
                                    'total_volume': pkg['Total Volume'],
                                    'total_cost': pkg['Total Cost']
                                })
                                if pkg['Total Cost']:
                                    total_cost_best_class += pkg['Total Cost']

                # Unfulfilled for best class
                unfulfilled_best = []
                for wc, unfulfilled in unfulfilled_files:
                    if wc == best_class:
                        unfulfilled_best.append({
                            'weight_class': wc,
                            'data_html': unfulfilled.to_html(index=False, classes='table table-striped table-bordered') if not unfulfilled.empty else '<p>No unfulfilled packages.</p>'
                        })

                # All fulfilled
                all_fulfilled = []
                for idx, (weight_class, packages) in enumerate(fulfilled_files.items()):
                    for pkg in packages:
                        all_fulfilled.append({
                            'package_idx': idx + 1,
                            'weight_class': weight_class,
                            'console_data_html': pkg['Console Data'].to_html(index=False, classes='table table-striped table-bordered'),
                            'total_weight': pkg['Total Weight'],
                            'total_volume': pkg['Total Volume'],
                            'total_cost': pkg['Total Cost']
                        })

                # All unfulfilled
                all_unfulfilled = []
                for weight_class, unfulfilled in unfulfilled_files:
                    all_unfulfilled.append({
                        'weight_class': weight_class,
                        'data_html': unfulfilled.to_html(index=False, classes='table table-striped table-bordered') if not unfulfilled.empty else '<p>No unfulfilled packages.</p>'
                    })

                # Comparative report
                comparative_data = []
                for weight_class, packages in fulfilled_files.items():
                    total_weight = sum(pkg['Total Weight'] for pkg in packages)
                    total_volume = sum(pkg['Total Volume'] for pkg in packages)
                    total_cost = sum(pkg['Total Cost'] if pkg['Total Cost'] is not None else 0 for pkg in packages)
                    
                    unfulfilled_weight = 0
                    unfulfilled_volume = 0
                    for wc, unfulfilled in unfulfilled_files:
                        if wc == weight_class:
                            unfulfilled_weight = unfulfilled['WEIGHT_TONS'].sum() if not unfulfilled.empty else 0
                            unfulfilled_volume = unfulfilled['CBM'].sum() if not unfulfilled.empty else 0
                    
                    comparative_data.append({
                        'Weight Class': weight_class,
                        'Total Consoles Made': len(packages),
                        'Total Weight Used (tons)': total_weight,
                        'Total Volume Used (CBM)': total_volume,
                        'Total Unfulfilled Weight (tons)': unfulfilled_weight,
                        'Total Unfulfilled Volume (CBM)': unfulfilled_volume,
                        'Total Cost': total_cost
                    })

                comparative_df = pd.DataFrame(comparative_data)
                comparative_html = comparative_df.to_html(index=False, classes='table table-striped table-bordered')

                context = {
                    'best_class': best_class,
                    'total_cost_best_class': total_cost_best_class,
                    'best_packages': best_packages,
                    'unfulfilled_best': unfulfilled_best,
                    'all_fulfilled': all_fulfilled,
                    'all_unfulfilled': all_unfulfilled,
                    'comparative_html': comparative_html,
                    'total_unfulfilled_count': len(unfulfilled_files)
                }

                return render(request, 'optimization/results.html', context)

            except Exception as e:
                return render(request, 'optimization/upload.html', {'form': form, 'error': str(e)})
    else:
        form = UploadForm()
    return render(request, 'optimization/upload.html', {'form': form})
