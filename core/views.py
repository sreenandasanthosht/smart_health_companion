"""
core app views -- the "chef" that prepares pages.
`home` gathers a little context and renders the home template.
"""
from django.shortcuts import render


def home(request):
    context = {
        'project_name': 'Smart Health Companion',
        'tagline': 'An Intelligent Integrated Health Management Ecosystem',
    }
    return render(request, 'core/home.html', context)
