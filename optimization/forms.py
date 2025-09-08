from django import forms

class UploadForm(forms.Form):
    uploaded_file = forms.FileField(label='Upload your data file (CSV or Excel)')
    volume_class = forms.ChoiceField(choices=[('DCD', 'DCD'), ('Other', 'Other')], initial='DCD', label='Select Volume Class')
    dcd_upper_limit = forms.FloatField(min_value=1.0, initial=58.0, label='Enter DCD Upper Limit')
    include_cost = forms.BooleanField(required=False, initial=True, label='Include Cost')
