import cgi
import flask
import operator
from jinja2 import Markup
from flask.ext import admin, wtf
from flask.ext.admin.model import BaseModelView

import taskpy.models.jobs
import taskpy.models.tasks
from taskpy.widgets.list import ExpandableFieldList

def format_status(view, context, model, field):
	'''Format status field to have an icon'''
	status = getattr(model, field)
	if not status:
		return Markup('<span class="label"><i class="icon-star-empty icon-white"></i> New</span>')
	elif status == "success":
		return Markup('<span class="label label-success"><i class="icon-thumbs-up icon-white"></i> Success</span>')
	else:
		return Markup('<span class="label label-important"><i class="icon-thumbs-down icon-white"></i> Failing</span>')

def format_name(view, context, model, field):
	'''Format job name as a link to the view page for that id'''
	url = flask.url_for('.job_view', id=getattr(model, field))
	return Markup('<a href="{url}">{field_value}</a>'.format(field_value=cgi.escape(getattr(model, field)), url=url))

def format_count(view, context, model, field):
	'''Format the task count in a badge'''
	return Markup('<div class="badge badge-inverse">%(field_value)s</div>') % {'field_value': len(getattr(model, field))}

class JobsNewForm(wtf.Form):
	'''Form for creating a new job'''
	name = wtf.StringField(
		  validators = [wtf.DataRequired(), wtf.Regexp('^[a-zA-Z0-9_\-]*$')]
		)

	def validate_name(self, field):
		if field.data in flask.g.configuration.jobs:
			raise wtf.ValidationError('That name already exists')

def task_name(task):
	if isinstance(task, taskpy.models.tasks.Task):
		return task.name
	return task

class JobEditForm(wtf.Form):
	'''Form for editing a job'''
	name = wtf.StringField(
		  validators = [wtf.DataRequired(), wtf.Regexp('^[a-zA-Z0-9_\-]*$')]
		)
	tasks = ExpandableFieldList(
		  wtf.SelectField(
			  'Task'
			, choices=[]
			, validators=[wtf.InputRequired()]
			, coerce=task_name
			)
		, min_entries=1
		)

	def validate_name(self, field):
		# Dont allow duplicate names
		# Only validate when changing name!
		if field.data != flask.request.args.get('id'):
			if field.data in flask.g.configuration.jobs:
				raise wtf.ValidationError('That name already exists')

class JobsView(BaseModelView):
	column_formatters = dict(status=format_status, name=format_name, tasks=format_count)
	column_labels = dict(name='Job Name')
	column_sortable_list = ['name', 'status', 'last_run']

	list_template='jobs.html'
	edit_template='job_edit.html'
	create_template='job_edit.html'

	def __init__(self, **options):
		super(JobsView, self).__init__(taskpy.models.jobs.Job, **options)

	def get_pk_value(self, model):
		return model.name

	def scaffold_list_columns(self):
		return ('name', 'tasks', 'status', 'last_run')

	def scaffold_form(self):
		return JobsNewForm

	def edit_form(self, obj):
		form = JobEditForm(obj=obj)

		# Fill in the task choices in the select boxes
		choices = [(x, x) for x in flask.g.configuration.tasks.keys()]
		for selector in form.tasks.entries:
			selector.choices = choices

		return form

	def get_one(self, name):
		return flask.g.configuration.jobs.get(name)

	def get_list(self, page, sort_field, sort_desc, search, filters):
		lst = [obj for name, obj in flask.g.configuration.jobs.iteritems()]
		# Setting default sort
		if sort_field == None:
			sort_field='name'
			sort_desc=1

		lst.sort(key=operator.attrgetter(sort_field), reverse=bool(sort_desc))
		return len(lst), lst

	def create_model(self, form):
		name = form.name.data

		try:
			model = taskpy.models.jobs.Job(name=name, configuration=flask.g.configuration)
			flask.g.configuration.add(model)
			flask.g.configuration.save()
			return True
		except Exception, ex:
			raise
			flask.flash('Failed to create. {}: {}'.format(ex.__class__.__name__, str(ex)), category='error')
			return False

	def delete_model(self, model):
		try:
			flask.g.configuration.remove(model)
			flask.g.configuration.save()
			return True
		except Exception, ex:
			raise
			flask.flash('Failed to delete. {}: {}'.format(ex.__class__.__name__, str(ex)), category='error')
			return False

	def update_model(self, form, model):
		try:
			# Handle renaming
			if model.name != form.name.data:
				flask.g.configuration.remove(model)
				model.name = form.name.data
				flask.flash('Renamed job to {}.'.format(model.name))

			# Handle tasks
			model.update_tasks(form.tasks.data)

			flask.g.configuration.add(model)
			flask.g.configuration.save()
			return True
		except Exception, ex:
			raise
			flask.flash('Failed to update. {}: {}'.format(ex.__class__.__name__, str(ex)), category='error')
			return False

	@admin.expose('/job/<id>')
	def job_view(self, id):
		job = self.get_one(id)
		if not job:
			return flask.redirect(flask.url_for('.index_view'))
		here = flask.url_for('.job_view', id=id)
		return self.render('job.html', job=job, return_url=here)

	@admin.expose('/job/<id>/run')
	def start_run_view(self, id):
		job = self.get_one(id)
		if not job:
			return flask.redirect(flask.url_for('.index_view'))
		job.run()
		return flask.redirect(flask.url_for('.job_view', id=id))

	@admin.expose('/job/<id>/runs/<run_id>')
	def run_view(self, id, run_id):
		job = self.get_one(id)
		if not job:
			return flask.redirect(flask.url_for('.job_view', id=id))
		run = job.get_run(run_id)
		if not run:
			return flask.redirect(flask.url_for('.job_view', id=id))
		here = flask.url_for('.run_view', id=id, run_id=run_id)
		return self.render('run.html', run=run, job=job, return_url=here)
