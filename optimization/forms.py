from django import forms
from .models import Dimensions, Containertypes

class UploadForm(forms.Form):
    # Container type selection
    container_type = forms.ChoiceField(
        choices=[
            ('console', 'Console'),
            ('closed_body_truck', 'Closed Body Truck')
        ],
        label='Select Container Type',
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'container_type'})
    )
    container_size = forms.MultipleChoiceField(
        choices=[],
        label='Select Container Size (Multi-select)',
        widget=forms.SelectMultiple(attrs={'class': 'form-select', 'id': 'container_size', 'multiple': 'multiple'})
    )

    # Dimensions selection will be handled via checkboxes in template
    selected_dimensions = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )

    include_cost = forms.BooleanField(
        required=False,
        initial=True,
        label='Include Cost',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate with all available sizes for form validation
        containers = Containertypes.objects.all()
        size_choices = []
        for container in containers:
            size_choices.append((f"{container.name} - {container.size}", f"{container.name} - {container.size}"))
        self.fields['container_size'].choices = size_choices
