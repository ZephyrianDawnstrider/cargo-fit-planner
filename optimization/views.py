from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from .forms import UploadForm
from .models import Dimensions, Containertypes
from .utils import optimize_packages, create_3d_model, get_color, mixed_bin_packing
import pandas as pd
import json
import os
import logging
from openpyxl import Workbook
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
import zipfile
from io import BytesIO
from decimal import Decimal
from datetime import datetime

logger = logging.getLogger(__name__)

def make_serializable(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif hasattr(obj, '_meta'):  # Django model
        return {field.name: make_serializable(getattr(obj, field.name)) for field in obj._meta.fields}
    elif isinstance(obj, dict):
        return {k: make_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [make_serializable(item) for item in obj]
    else:
        return obj

def upload_view(request):
    if request.method == 'POST':
        form = UploadForm(request.POST)
        if form.is_valid():
            container_type = form.cleaned_data['container_type']
            container_sizes = form.cleaned_data['container_size']
            selected_dimensions_ids = form.cleaned_data.get('selected_dimensions', '')
            # include_cost = form.cleaned_data['include_cost']

            try:
                # Determine categorytypeid based on container type
                if container_type == 'console':
                    categorytypeid = 7
                elif container_type == 'closed_body_truck':
                    categorytypeid = 8
                else:
                    return render(request, 'optimization/upload.html', {'form': form, 'error': 'Invalid container type selected.'})

                # Handle multiple container sizes
                if not container_sizes:
                    return render(request, 'optimization/upload.html', {'form': form, 'error': 'Please select at least one container size.'})

                containers = []
                total_volume = 0
                total_max_weight = 0

                for container_size in container_sizes:
                    container = Containertypes.objects.filter(
                        categorytypeid=categorytypeid,
                        name=container_size.split(' - ')[0] if ' - ' in container_size else container_size,
                        size=container_size.split(' - ')[1] if ' - ' in container_size else container_size
                    ).first()

                    if container:
                        containers.append(container)
                        total_volume += float(container.volume_cbm)
                        total_max_weight += float(container.maxpayload_kg) / 1000  # Convert to tons
                    else:
                        # Try to find a default container for this category
                        default_container = Containertypes.objects.filter(
                            categorytypeid=categorytypeid
                        ).first()
                        if default_container:
                            containers.append(default_container)
                            total_volume += float(default_container.volume_cbm)
                            total_max_weight += float(default_container.maxpayload_kg) / 1000

                if not containers:
                    return render(request, 'optimization/upload.html', {'form': form, 'error': 'No valid containers found.'})

                # Check if all container sizes for the category are selected
                total_sizes = Containertypes.objects.filter(categorytypeid=categorytypeid).count()
                all_selected = len(container_sizes) == total_sizes

                # Get selected dimensions
                if selected_dimensions_ids:
                    selected_ids = [int(id.strip()) for id in selected_dimensions_ids.split(',') if id.strip()]
                    dimensions = Dimensions.objects.filter(id__in=selected_ids)
                else:
                    dimensions = Dimensions.objects.all()

                # Convert to DataFrame for processing
                data = pd.DataFrame(list(dimensions.values(
                    'queryid', 'id', 'Lenght', 'Breadth', 'Height', 'WeightPerUnit',
                    'TotalUnits', 'PackageType', 'CargoType', 'BasePackageWeight', 'dimensionunit'
                )))

                if data.empty:
                    return render(request, 'optimization/upload.html', {'form': form, 'error': 'No dimensions data available.'})

                # Get selected data
                selected_ids = [int(id.strip()) for id in selected_dimensions_ids.split(',') if id.strip()] if selected_dimensions_ids else []
                selected_data = data[data['id'].isin(selected_ids)] if selected_ids else data

                # Expand data by TotalUnits
                selected_data_expanded = []
                for index, row in selected_data.iterrows():
                    try:
                        units = int(row['TotalUnits'])
                        if units <= 0:
                            logger.warning(f"Skipping row {index}: TotalUnits = {row['TotalUnits']} (not positive)")
                            continue
                    except (ValueError, TypeError):
                        logger.warning(f"Skipping row {index}: Invalid TotalUnits = {row['TotalUnits']}")
                        continue
                    lenght = float(row['Lenght'])
                    breadth = float(row['Breadth'])
                    height = float(row['Height'])
                    dimensionunit = row['dimensionunit'].lower()
                    weight_unit = row['WeightPerUnit'].lower() if row['WeightPerUnit'] else 'kg'
                    base_weight = float(row['BasePackageWeight'])
                    cargo_type = row['CargoType']

                    # Convert dimensions to cm
                    if dimensionunit == 'm' or dimensionunit == 'meter':
                        lenght *= 100
                        breadth *= 100
                        height *= 100
                    elif dimensionunit == 'inch' or dimensionunit == 'in':
                        lenght *= 2.54
                        breadth *= 2.54
                        height *= 2.54
                    elif dimensionunit == 'yard' or dimensionunit == 'yd':
                        lenght *= 91.44
                        breadth *= 91.44
                        height *= 91.44
                    elif dimensionunit == 'feet' or dimensionunit == 'ft':
                        lenght *= 30.48
                        breadth *= 30.48
                        height *= 30.48
                    # Assume cm if not specified or unknown

                    # Convert weight to kg
                    if weight_unit in ['ton', 'tons', 't']:
                        base_weight *= 1000
                    elif weight_unit == 'g' or weight_unit == 'gram':
                        base_weight /= 1000
                    elif weight_unit == 'lb' or weight_unit == 'pound':
                        base_weight *= 0.453592
                    # Assume kg if not specified or unknown

                    # Adjust dimensions based on type
                    if cargo_type == 'Dangerous Goods':
                        lenght += 10  # +10 cm
                        breadth += 10
                        height += 10
                    elif cargo_type == 'Over-Dimension Cargo':
                        lenght *= 1.1  # +10%
                        breadth *= 1.1
                        height *= 1.1

                    volume_cbm = (lenght * breadth * height) / 1000000
                    weight_per_unit_kg = base_weight
                    weight_tons = weight_per_unit_kg / 1000

                    for _ in range(units):
                        selected_data_expanded.append({
                            'queryid': row['queryid'],
                            'id': row['id'],
                            'Lenght': lenght,
                            'Breadth': breadth,
                            'Height': height,
                            'WeightPerUnit': row['WeightPerUnit'],
                            'PackageType': row['PackageType'],
                            'CargoType': row['CargoType'],
                            'BasePackageWeight': row['BasePackageWeight'],
                            'weight_tons': weight_tons,
                            'volume_cbm': volume_cbm
                        })
                selected_data_expanded = pd.DataFrame(selected_data_expanded)
                logger.info(f"Expanded data to {len(selected_data_expanded)} individual items from {len(selected_data)} selected records.")

                # Get all available containers for the category
                available_containers = list(Containertypes.objects.filter(categorytypeid=categorytypeid))
                logger.info(f"Available containers for category {categorytypeid}: {[f'{c.name}-{c.size}' for c in available_containers]}")

                # Perform mixed bin packing
                output_dir = 'optimization/static/optimization'
                logger.info(f"Calling mixed_bin_packing with {len(selected_data_expanded)} items, {len(available_containers)} containers, output_dir {output_dir}")
                containers_used, model_images, remaining_df = mixed_bin_packing(selected_data_expanded, available_containers, output_dir)
                logger.info(f"Mixed bin packing result: {len(containers_used)} containers used, {len(model_images)} models, {len(remaining_df)} remaining items")

                # Build scenario
                num_containers = len(containers_used)
                remaining_items = remaining_df.to_dict('records') if not remaining_df.empty else []
                for item in remaining_items:
                    item['color'] = get_color(item['queryid'], item['id'])
                total_weight_remaining = sum(item['weight_tons'] for item in remaining_items) if remaining_items else 0
                total_volume_remaining = sum(item['volume_cbm'] for item in remaining_items) if remaining_items else 0

                scenario_name = f"Mixed Containers: {num_containers} containers, {len(remaining_items)} remaining"
                scenarios = [{
                    'name': scenario_name,
                    'containers_used': containers_used,
                    'remaining_items': remaining_items,
                    'total_weight_remaining': total_weight_remaining,
                    'total_volume_remaining': total_volume_remaining,
                    'model_images': model_images
                }]

                # Create container names string for display (all available)
                container_names = [f"{c.name} - {c.size}" for c in available_containers]
                selected_containers_str = ", ".join(container_names)

                # Calculate total max weight and volume for all available
                total_max_weight = sum(float(c.maxpayload_kg) / 1000 for c in available_containers if c.maxpayload_kg)
                total_volume = sum(float(c.volume_cbm) for c in available_containers if c.volume_cbm)

                # Store scenarios in session for download (serialize to avoid JSON issues)
                request.session['scenarios'] = make_serializable(scenarios)

                context = {
                    'scenarios': scenarios,
                    'selected_container': selected_containers_str,
                    'max_weight': total_max_weight,
                    'container_volume': total_volume
                }

                return render(request, 'optimization/results.html', context)

            except Exception as e:
                logger.error(f"Exception occurred in upload_view: {str(e)}")
                return render(request, 'optimization/upload.html', {'form': form, 'error': str(e)})
    else:
        form = UploadForm()

    # Get dimensions for display
    dimensions = Dimensions.objects.all()
    unique_cargo_types = list(Dimensions.objects.values_list('CargoType', flat=True).distinct())
    context = {
        'form': form,
        'dimensions': dimensions,
        'unique_cargo_types': unique_cargo_types
    }
    return render(request, 'optimization/upload.html', context)


def get_container_sizes(request, categorytypeid):
    containers = Containertypes.objects.filter(categorytypeid=categorytypeid)
    sizes = [f"{c.name} - {c.size}" for c in containers]
    return JsonResponse({'sizes': sizes})


def download_plan(request, format_type):
    scenarios = request.session.get('scenarios')
    if not scenarios:
        return HttpResponse("No data available for download.", status=404)

    scenario = scenarios[0]  # Assuming first scenario

    if format_type == 'excel':
        wb = Workbook()
        ws_summary = wb.active
        ws_summary.title = "Summary"
        ws_summary.append(["Container", "Total Weight (tons)", "Total Volume (CBM)", "Total Items"])

        for container in scenario['containers_used']:
            ws_summary.append([
                f"{container['container']['name']} - {container['container']['size']} (Instance {container['container_number']})",
                container['total_weight'],
                container['total_volume'],
                len(container['items'])
            ])

            ws = wb.create_sheet(title=f"Container {container['container_number']}")
            ws.append(["Order", "Query ID", "ID", "Package Type", "Cargo Type", "Dimensions (L×W×H CM)", "Weight (tons)", "Volume (CBM)"])
            for idx, item in enumerate(container['items'], 1):
                ws.append([
                    idx,
                    item['queryid'],
                    item['id'],
                    item['PackageType'],
                    item['CargoType'],
                    f"{item['Lenght']} × {item['Breadth']} × {item['Height']}",
                    item['weight_tons'],
                    item['volume_cbm']
                ])

        buffer = BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename=optimization_plan.xlsx'
        return response

    elif format_type == 'pdf':
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()

        elements.append(Paragraph("Optimization Plan", styles['Title']))

        for container in scenario['containers_used']:
            elements.append(Paragraph(f"Container: {container['container']['name']} - {container['container']['size']} (Instance {container['container_number']})", styles['Heading2']))
            data = [["Order", "Query ID", "ID", "Package Type", "Cargo Type", "Dimensions", "Weight (tons)", "Volume (CBM)"]]
            for idx, item in enumerate(container['items'], 1):
                data.append([
                    str(idx),
                    str(item['queryid']),
                    str(item['id']),
                    item['PackageType'],
                    item['CargoType'],
                    f"{item['Lenght']} × {item['Breadth']} × {item['Height']} CM",
                    f"{item['weight_tons']:.4f}",
                    f"{item['volume_cbm']:.4f}"
                ])
            table = Table(data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), '#f0f0f0'),
                ('TEXTCOLOR', (0, 0), (-1, 0), '#000000'),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), '#ffffff'),
                ('GRID', (0, 0), (-1, -1), 1, '#000000'),
            ]))
            elements.append(table)
            elements.append(Paragraph("", styles['Normal']))

        doc.build(elements)
        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename=optimization_plan.pdf'
        return response

    elif format_type == '3d':
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, 'w') as zip_file:
            for image in scenario['model_images']:
                file_path = os.path.join('optimization/static', image)
                if os.path.exists(file_path):
                    zip_file.write(file_path, os.path.basename(file_path))
        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type='application/zip')
        response['Content-Disposition'] = 'attachment; filename=3d_models.zip'
        return response

    return HttpResponse("Invalid format.", status=400)
