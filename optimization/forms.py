from django import forms

class UploadForm(forms.Form):
    uploaded_file = forms.FileField(
        label='Upload your data file (CSV or Excel)',
        widget=forms.ClearableFileInput(attrs={'class': 'form-control'})
    )
    volume_class = forms.ChoiceField(
        choices=[('DCD', 'DCD'), ('Other', 'Other')],
        initial='DCD',
        label='Select Volume Class',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    dcd_upper_limit = forms.FloatField(
        min_value=1.0,
        initial=58.0,
        label='Enter DCD Upper Limit',
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    include_cost = forms.BooleanField(
        required=False,
        initial=True,
        label='Include Cost',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )