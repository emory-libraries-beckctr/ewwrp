import os
import re

from forms import *
from models import *

import time

from itertools import chain

from settings import COLLECTIONS, DEFAULT_COLLECTION, DEFAULT_ORDERING

from django.conf import settings
from django.http import Http404
from django.shortcuts import render_to_response, redirect, HttpResponse, Http404
from django.template import RequestContext

import json

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

''' Helper methods for views '''
def isInt(n):
    ''' Check if a string can be converted to an int or not '''
    try:
        if not n:
            return False
        int(n)
        return True
    except ValueError:
        return False

def getIntRange(n):
	m = re.search(r'^(?P<start>\d+)to(?P<end>\d+)$',n)
	if m:
		return m
	else:
		return False

def safeRange(r, a, b):
	''' Returns r[a:b] in a safe way '''
	lr = len(r)
	if a < 0: a = 0
	if b < 0: b = 0
	if a >= lr: a = lr-1
	if b >= lr: b = lr-1
	if a > b: return r[b:a]
	return r[a:b]

def makeURL(**kwargs):
    return '?' + '&'.join("{!s}={!s}".format(key,val) for (key,val) in kwargs.items())

def valueOrDefault(request, val, default_value):
    try:
        if request.method == 'POST':
            if val not in request.POST:
                return default_value
            try:
                int(default_value)
                return int(request)
            except ValueError:
                return request.POST[val]
        elif request.method == 'GET':
            if val not in request.GET:
                return default_value
            try:
                int(default_value)
                return int(request)
            except ValueError:
                return request.GET[val]
    except ValueError:
        return default_value

def importantContextValues(app):
    ''' Values that should be available from any template. This is basically a work-around for managing apps '''
    return {'app': COLLECTIONS[app], 'collections': COLLECTIONS, 'can_sort_by': (('Author','author'), ('Title','title')), 'res_per_page': ((10,10), (20,20), (50,50))}
''' End helper methods '''

def req(request):
    ''' AJAX method for rendering page '''
    if request.is_ajax():
        try:
            start_time = time.time()
            toReturn = {}
            current_page = valueOrDefault(request, 'current_page', 1)
            results_per_page = valueOrDefault(request, 'results_per_page', 10)
    
            # Parse for search options
            search_opts = {}
            if 'title' in request.POST and request.POST['title']:
                search_opts['title__fulltext_terms'] = request.POST['title']
            if 'author' in request.POST and request.POST['author']:
                search_opts['author__fulltext_terms'] = request.POST['author']
            if 'keyword' in request.POST and request.POST['keyword']:
                search_opts['fulltext_terms'] = request.POST['keyword']
            if 'collection' in request.POST and request.POST['collection']:
                if isinstance(request.POST['collection'],str):
                    search_opts['collection__in'] = COLLECTIONS[request.POST['collection']]['name']
                elif isinstance(form.cleaned_data['collection'],list):
                    search_opts['collection__in'] = [COLLECTIONS[m]['name'] for m in request.POST['collection']]
            
            pageobjs = Docs.objects.filter(**search_opts).order_by('-fulltext_score')
                
            # Order by user-specified criteria, if they do specify it
            if 'sort_by' in request.POST and len(request.POST['sort_by'])>0:
                pageobjs = pageobjs.order_by(request.GET['sort_by'])
                context['sort_by'] = request.POST['sort_by']
            
            # Create paginator safely
            paginator = Paginator(pageobjs, results_per_page)
            try:
                pages = paginator.page(current_page)
            except EmptyPage:
                pages = paginator.page(paginator.num_pages)
            
            if pages.has_previous():
                toReturn['previous_page_number'] = pages.previous_page_number
            if pages.has_next():
                toReturn['next_page_number'] = pages.next_page_number
            
            print 'Time is', (time.time() - start_time)
            return HttpResponse(json.dumps(toReturn), content_type='application/json')
        except Exception, e:
            print e
            return HttpResponse(json.dumps({'error': e}), content_type='application/json')
    else:
        return Http404

def search(request, method='basic', app=DEFAULT_COLLECTION):
    ''' Search for a document within a collection, using either basic or advanced search '''
    context = importantContextValues(app)
    
    # Determine whether or not to do an advanced search
    if method == 'advanced':
        context['page_in_collection'] = 'advsearch'
        context['advanced'] = True
        if request.GET: form = AdvancedSearchForm(request.GET)
        else: form = AdvancedSearchForm()
    else:
        context['page_in_collection'] = 'search'
        context['advanced'] = False
        if request.GET: form = SearchForm(request.GET)
        else: form = SearchForm()
    
    # Pass the form variable to the context instance
    context['form'] = form
    
    # If they didn't search yet, render the page as is
    if not request.GET or not form.is_valid():
        return render_to_response('search.html', context, context_instance=RequestContext(request))
    
    # Copy over the queries, e.g. current page number
    queries = request.GET.copy()
    return render_to_response('search.html',context,context_instance=RequestContext(request))

def page(request, doc_id, page, app=DEFAULT_COLLECTION):
    ''' Display a specific page '''
    context = {'app': COLLECTIONS[app]}
    context['page_in_collection'] = 'page'
    document = Docs.objects.get(id=doc_id)
    context['document'] = document
    if page != 'contents':
        # Create ordered list of all the divs
        id_list = [i.id for i in document.divs]
        
        # Position of current id
        position = id_list.index(page)
        
        # Get the current page
        docpage = document.divs[position]
        
        # Get ID of prev and next pages
        if position > 0:
            context['prev_id'] = id_list[position-1]
        if position+1 < len(id_list):
            context['next_id'] = id_list[position+1]
        
        # Get the current page
        context['docpage'] = docpage
        
        # Apply xsl transform
        formatted = docpage.xsl_transform(filename=os.path.join('file:///' + settings.BASE_DIR, 'ewwrp', 'static', 'xsl', 'tei.xsl'))
        context['formatted'] = formatted.serialize()
    context['page'] = page
    return render_to_response('page.html',context,context_instance=RequestContext(request))

def index(request, app=DEFAULT_COLLECTION):
    ''' Home page '''
    context = importantContextValues(app)
    context['page_in_collection'] = 'index'
    return render_to_response('index.html',context,context_instance=RequestContext(request))

def about(request, app=DEFAULT_COLLECTION):
    ''' About page - just a regular html file '''
    context = importantContextValues(app)
    context['page_in_collection'] = 'about'
    return render_to_response('about.html',context,context_instance=RequestContext(request))

def essays(request, essay_id='all', app=DEFAULT_COLLECTION):
    ''' Essays - still need to make this work, but it should be quick '''
    context = importantContextValues(app)
    context['page_in_collection'] = 'essays'
    
    # Copy GET info over to a variable
    queries = request.GET.copy()
    
    # If the user is on a certain page, get that page and remove it from the query; otherwise, default to first page
    if 'current_page' in request.GET and isInt(request.GET['current_page']):
        current_page = int(request.GET['current_page'])
        del queries['current_page']
    else:
        current_page = 1
    
    # If the user specified the number of results per page, use that. Default to 10.
    if 'results_per_page' in request.GET and isInt(request.GET['results_per_page']):
        results_per_page = int(request.GET['results_per_page'])
    else:
        results_per_page = 10
    context['results_per_page'] = results_per_page
    
    if essay_id == 'all':
        # Get all the essays in this app
        filt = {'collection__in': COLLECTIONS[app]['name']}
        pageobjs = Essays.objects.filter(filt)
    else:
        # Get a specific essay and deliver it
        pageobjs = Essays.objects.get(id=essay_id)
    
    # Order by user-specified criteria
    if 'sort_by' in request.GET and len(request.GET['sort_by'])>0:
        pageobjs = pageobjs.order_by(request.GET['sort_by'])
        context['sort_by'] = request.GET['sort_by']

    # Pass the GET data, minus current page, to the context
    context['queries'] = queries
    
    paginator = Paginator(pageobjs, results_per_page)

    try:
        pages = paginator.page(current_page)
    except PageNotAnInteger:
        pages = paginator.page(1)
    except EmptyPage:
        pages = paginator.page(paginator.num_pages)

    context['pages'] = pages

    return render_to_response('essays.html',context,context_instance=RequestContext(request))

# This could use being updated
def browse(request, app=DEFAULT_COLLECTION):
    ''' Browse the collection '''
    context = importantContextValues(app)
    context['page_in_collection'] = 'browse'
    
    # Copy GET info over to a variable
    queries = request.GET.copy()
    
    # If the user is on a certain page, get that page and remove it from the query; otherwise, default to first page
    if 'current_page' in request.GET and isInt(request.GET['current_page']):
        current_page = int(request.GET['current_page'])
        del queries['current_page']
    else:
        current_page = 1
    
    # If the user specified the number of results per page, use that. Default to 10.
    if 'results_per_page' in request.GET and isInt(request.GET['results_per_page']):
        results_per_page = int(request.GET['results_per_page'])
    else:
        results_per_page = 10
    context['results_per_page'] = results_per_page
    
    # Get all the documents in the current collection
    if app != DEFAULT_COLLECTION:
        pageobjs = Docs.objects.filter(collection=COLLECTIONS[app]['name']).all()
    else:
        # If in the default collection don't filter
        pageobjs = Docs.objects.all()
    
    # Order by user-specified criteria
    if 'sort_by' in request.GET and len(request.GET['sort_by'])>0:
        pageobjs = pageobjs.order_by(request.GET['sort_by'])
        context['sort_by'] = request.GET['sort_by']
    else:
        pageobjs = pageobjs.order_by(DEFAULT_ORDERING)
        context['sort_by'] = DEFAULT_ORDERING

    # Pass the GET data, minus current page, to the context
    context['queries'] = queries
    
    paginator = Paginator(pageobjs, results_per_page)

    try:
        pages = paginator.page(current_page)
    except PageNotAnInteger:
        pages = paginator.page(1)
    except EmptyPage:
        pages = paginator.page(paginator.num_pages)

    context['pages'] = pages

    return render_to_response('browse.html',context,context_instance=RequestContext(request))