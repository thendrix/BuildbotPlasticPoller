# Quick hack of XyPlasticPoller.py to provide Plastic SCM polling ChangeSource
# @author Terry Hendrix II
# This software is generously provided by PaddleCreekGames
# PaddleCreekGames reserves the right to distribute under other Licenses.
#
# MIT License
#
# Copyright (c) 2017 Paddle Creek Games
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import itertools
import os
import re
import sys
import subprocess
import urllib
import datetime
from dateutil import tz

from twisted.internet import defer
from twisted.internet import utils
from twisted.python import log

from buildbot import config
from buildbot.changes import base
from buildbot.util import epoch2datetime
from buildbot.util.state import StateMixin


# @class XyLog
# @brief Simple logging wrapper for redirection.
class XyLog:
	@staticmethod
	def Debug( text, redirect=None ):
		print text

	@staticmethod
	def Error( text, redirect=None ):
		print '== ERROR == ' + text

	@staticmethod
	def Print( text, redirect=None ):
		print text


# @class XyResult
# @brief Unified return code system that allows for better cross module error handling.
class XyResult:
	Ok, Error, Unknown = range(3)

	@staticmethod
	def FromShell(returnCode):
		return XyResult.Ok if returnCode is 0 else XyResult.Error

	@staticmethod
	def ToShell(result):
		return 0 if result is XyResult.Ok else -1


# @class XyPlasticScm
# @brief Plastic SCM connector via plastic CLI wrapper.
class XyPlasticScm:
	## Constructor required, not a pure staticmethod class.
	def __init__(self, root, repo_='FRVContent', branch_='main'):
		## Application name.
		self.__cm = 'cm'

		## Default working path.
		self.__root = root

		## Enable logging for command debugging and status logging.
		self.__debug = False

		self.__branch = branch_

		self.__repo = repo_

		## DEBUG Enable extra logging for debugging.
		self.__debug = False

		## DEBUG Do not execute commands, only dump command arrays.
		self.__debugMock = False

		## End of Line for SCM query markup
		self.__eol = '@eol@'

		## Seperator for SCM query markup
		self.__sep = '@sep@'


	def __Environ(self):
		env = os.environ.copy()
		if sys.platform == 'linux2':
			opt = '/opt/plasticscm5/client'
			if os.path.isdir(opt):
				env['PATH'] += ':' + opt

		if sys.platform == 'win32':
			if os.path.isdir('C:\\opt\\PlasticSCM5\\client\\'):
				env['PATH'] += ';' + 'C:\\opt\\PlasticSCM5\\client\\'
			if os.path.isdir('C:\\Program Files\\PlasticSCM5\\client\\'):
				env['PATH'] += ';' + 'C:\\Program Files\\PlasticSCM5\\client\\'

		return env


	## Execute command on shell with optional output streams ( blocking ).
	# @return Numeric error code from shell for caller handling.
	def __Shell(self, tag_, cmd_, wdir_, logging_=True, stdout_=None, stderr_=None, shell_=False, env_=None, input_=None ):
		if logging_:
			# @todo - Don't currently log as buildbot captures these.
			XyLog.Print( '[' + tag_ + '] ' + wdir_ + ' $ ' + str( ' '.join(cmd_) )  )
			# XyLog.Log( tag, wdir + ' $ ' + str( ' '.join( cmd ) )  )

		if env_ is None:
			env_ = os.environ.copy()

		if cmd_ is None:
			XyLog.Error("Shell(): Invalid command.")
			return -1

		ret = -1 #XyResult.Error
		if stdout_ and stderr_:
			# redirect out/err in a thread safe manner w/o using file I/O for now.
			try:
				p = subprocess.Popen(cmd_, shell=shell_,
					stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE, 
					cwd=wdir_, env=env_)
				out, err = p.communicate(input_)
				stdout_.append(out)
				stderr_.append(err)
				ret = p.returncode

			except Exception, e:
				XyLog.Print( str(e) )

		elif input_:
			# redirect out/err in a thread safe manner w/o using file I/O for now.
			try:
				p = subprocess.Popen(cmd_, shell=shell_, stdin=subprocess.PIPE, cwd=wdir_, env=env_)
				p.communicate(input_)
				ret = p.returncode

			except Exception, e:
				XyLog.Print( str(e) )

		else:
			try:
				ret = subprocess.call(cmd_, cwd=wdir_, shell=shell_, env=env_)
			except Exception, e:
				XyLog.Print( str(e) )

		return ret


	## WAR for bad SSL cert on server; This will accept insecure connection prompt.
	def __Exec(self, query, stdoutCapture=None, stderrCapture=None):
		newline = os.linesep
		# WAR This interactively answers 'y' to the prompt to continue.
		interactivecmds = ['y']
		tag = 'XyPlasticScm.Exec'
		cmd = [self.__cm]
		cmd.extend(query)
		ret = self.__Shell(tag, cmd, self.__root, self.__debug
			,shell_=False
			,env_=self.__Environ()
			,stdout_=stdoutCapture
			,stderr_=stderrCapture
			# WAR This interactively answers 'y' to the prompt to continue.
			,input_=newline.join(interactivecmds)
			)

		# WAR Remove the SSL cert warning from stdout if found.
		if self.__ValidCapture(stdoutCapture):
			wedge = "Choose an option (Y)es, (N)o (hitting Enter selects 'No'): "
			if wedge in stdoutCapture[1]:
				stdoutCapture[1] = stdoutCapture[1].split(wedge)[1]

		if self.__debug and self.__ValidCapture(stdoutCapture):
			XyLog.Debug(stdoutCapture[1])

		if self.__ValidCapture(stderrCapture):
			XyLog.Error('XyPlasticScm.__Exec(): ' + stderrCapture[1])

		return XyResult.FromShell(ret)


	## Test if the capture from stdout or stderr is valid.
	def __ValidCapture(self, pipe_):
		return True if ( pipe_ and len(pipe_) > 1 and pipe_[1] ) else False


	def Branch(self):
		return self.__branch


	## List branch names for current repository.
	# This query works without a workspace.
	# @return XyResult.Ok on success
	def Branches(self, branches_, stripRoot_=True):
		# Complex queries need special formatting or get chewed up by Windows shell.
		# query = ['find', 'branches', 'where', "changesets >= '1/1/2017'",
		# 	'--nototal', 'on', 'repositories \''+self.__repo+'\'' ]
		query = ['find', 'branches',
			'--format={name}',
			'--nototal', 'on', 'repositories \''+self.__repo+'\'' ]
		stdoutCapture = ['stdout']
		stderrCapture = ['stderr']
		result = self.__Exec(query, stdoutCapture, stderrCapture)
		if result == XyResult.Ok and stdoutCapture[1]:
			lines = stdoutCapture[1].split(os.linesep)
			for line in lines:
				if line:
					if stripRoot_:
						branches_.append(line[1:])
					else:
						branches_.append(line)
				# XyLog.Debug(branches_)
		return result


	## Query a changeset by id
	def Changes(self, id_, changes_, files_=None, branch_=None):
		if branch_ is None:
			branch_ = self.Branch()

		# Complex queries need special formatting or get chewed up by Windows shell.
		eol = self.__eol # '@#eol#@'
		st = self.__sep # '@#st#@'
		query = [ 'find', 'changeset', 'where', "branch='" + branch_ + "'",
			'and', "changesetid = " + str(id_),
			'--format={changesetid}'+st+'{guid}'+st+'{owner}'+st+'{date}'+st+'{comment}'+eol,
			'--nototal', 'on', 'repositories \''+self.__repo+'\'' ]
		stdoutCapture = ['stdout']
		stderrCapture = ['stderr']
		result = self.__Exec(query, stdoutCapture, stderrCapture)
		if result == XyResult.Ok and self.__ValidCapture(stdoutCapture):
			lines = stdoutCapture[1].split(eol+os.linesep)
			for line in lines:
				if line:
					change = line.split(st)
					if files_ is not None:
						change.append(files_)
					changes_.append(change)
					# XyLog.Debug(change)
		return result


	def ChangesAfter(self, changes_, id_, branch_=None):
		if branch_ is None:
			branch_ = self.Branch()

		# Complex queries need special formatting or get chewed up by Windows shell.
		eol = self.__eol # '@#eol#@'
		st = self.__sep # '@#st#@'
		query = [ 'find', 'changeset', 'where', "branch='" + self.__branch + "'",
			'and', "changesetid > " + str(id_),
			'--format={changesetid}'+st+'{guid}'+st+'{owner}'+st+'{date}'+st+'{comment}'+eol,
			'--nototal', 'on', 'repositories \''+self.__repo+'\'' ]
		stdoutCapture = [ 'stdout' ]
		stderrCapture = [ 'stderr' ]
		result = self.__Exec(query, stdoutCapture, stderrCapture)
		if result == XyResult.Ok and self.__ValidCapture(stdoutCapture):
			lines = stdoutCapture[1].split(eol+os.linesep)
			for line in lines:
				if line:
					change = line.split(st)
					changes_.append(change)
					# XyLog.Debug(change)
		return result


	def Changeset(self, value):
		# Complex queries need special formatting or get chewed up by Windows shell.
		query = ['find', 'branch', 'where', "name='"+self.__branch+"'",
			'--format={changeset}', '--nototal', 'on', 'repositories',
			"'" + self.__repo + "'" ]
		stdoutCapture = [ 'stdout' ]
		stderrCapture = [ 'stderr' ]
		result = self.__Exec(query, stdoutCapture, stderrCapture)
		if result == XyResult.Ok and stdoutCapture[1]:
			# revision = stdoutCapture[1].rsplit(None, 1)[1]
			revision = stdoutCapture[1]
			# XyLog.Debug('Latest revision: ' + revision)
			value[0] = int(revision)
		return result


	def LastChangesetId(self):
		eol = self.__eol
		sep = self.__sep
		stdoutCapture = ['stdout']
		stderrCapture = ['stderr']
		query = [ 'find', 'branch', 'where', "name='" + self.__branch + "'",
			'--format={changeset}'+eol,
			'--nototal', 'on', 'repositories \''+self.__repo+'\'' ]
		result = self.__Exec(query, stdoutCapture, stderrCapture)
		if result == XyResult.Ok and stdoutCapture[1]:
			lines = stdoutCapture[1].split(eol+os.linesep)
			if lines and lines[0]:
				return int(lines[0])
		return -1


	def LookupMergeId(self, branch_, changesetid_, result_):
		eol = self.__eol
		sep = self.__sep
		# Complex queries need special formatting or get chewed up by Windows shell.
		stdoutCapture = ['stdout']
		stderrCapture = ['stderr']
		query = [ 'find', 'merge', 'where', "dstbranch='" + branch_ + "'",
			'and', "dstchangeset=" + str(changesetid_),
			'--format={type}'+sep+'{srcbranch}'+sep+'{srcchangeset}'+eol,
			'--nototal', 'on', 'repositories \''+self.__repo+'\'' ]
		result = self.__Exec(query, stdoutCapture, stderrCapture)
		if result == XyResult.Ok and stdoutCapture[1]:
			lines = stdoutCapture[1].split(eol+os.linesep)
			for line in lines:
				if line:
					change = line.split(sep)
					result_.extend(change)
					# XyLog.Debug(change)
		return result


	def MergeChanges(self, branch_, id_, changes_):
		# if branch_ is None:
		# 	branch_ = self.__branch

		# Complex queries need special formatting or get chewed up by Windows shell.
		eol = self.__eol # '@#eol#@'
		st = self.__sep # '@#st#@'
		query = [ 'find', 'merges', 'where', "dstbranch='" + branch_ + "'",
			'and', "srcchangeset = " + str(id_),
			'--format={srcchangeset}'+st+'{srcbranch}'+eol,
			'--nototal', 'on', 'repositories \''+self.__repo+'\'' ]
		stdoutCapture = [ 'stdout' ]
		stderrCapture = [ 'stderr' ]
		result = self.__Exec(query, stdoutCapture, stderrCapture)
		if result == XyResult.Ok and stdoutCapture[1]:
			lines = stdoutCapture[1].split(eol+os.linesep)
			for line in lines:
				if line:
					change = line.split(st)
					changes_.append(change)
					# XyLog.Debug(change)
		return result


	def MergesAfter(self, changes_, id_):
		# Complex queries need special formatting or get chewed up by Windows shell.
		eol = self.__eol # '@#eol#@'
		st = self.__sep # '@#st#@'
		query = [ 'find', 'merges', 'where', "dstbranch='" + self.__branch + "'",
			'and', "srcchangeset > " + str(id_),
			'--format={srcchangeset}'+st+'{srcbranch}'+eol,
			'--nototal', 'on', 'repositories \''+self.__repo+'\'' ]
		stdoutCapture = [ 'stdout' ]
		stderrCapture = [ 'stderr' ]
		result = self.__Exec(query, stdoutCapture, stderrCapture)
		if result == XyResult.Ok and stdoutCapture[1]:
			lines = stdoutCapture[1].split(eol+os.linesep)
			for line in lines:
				if line:
					change = line.split(st)
					changes_.append(change)
					# XyLog.Debug(change)
		return result


	## Gather lists of merges, changesets of merges, and files of merges into repo:branch after changeset id_
	# Can be called multiple times to append results.
	# This does a lot of subqueries due to how merge changesets work. (Slow)
	def MergeChangesetsAfter(self, id_, merges_, changesets_, files_):
		merges = []
		result = self.MergesAfter(merges, id_)
		# if self.__debug:
		# 	XyLog.Debug( 'MERGES : \n' + str(merges) )
		merges_.extend(merges)

		changesets = []
		last = -1
		for merge in merges:
			# Filter out empty merge
			if merge and len(merge) > 1 and merge[0] and merge[1]:
				changesetid = merge[0]
				branch = merge[1]
				cid = int(changesetid)
				if cid > last:
					last = cid

				# XyLog.Debug( 'MERGE : ' + changesetid + ', ' + branch )

				# Remap merged files back to the 'root' of the destination branch.
				files = []
				self.RevisionFilesOnly(files, changesetid, '/'+self.Repo()+'/'+self.Branch(), branch_=branch)
				files_.extend(files)
				self.Changes(changesetid, changesets, files, branch_=branch)

		changesets_.extend(changesets)

		# print( 'FILES : \n' + str(files) )
		# print( 'CHANGESETS : \n' + str(changesets) )
		return last


	def Repo(self):
		return self.__repo


	def Revision(self, files_, id_, preamble_=''):
		# Complex queries need special formatting or get chewed up by Windows shell.
		query = ['find', 'revision', 'where', "branch='"+self.__branch+"'",
			'and', 'changeset='+str(id_),
			'--format={path}', '--nototal', 'on', 'repositories', "'" + self.__repo + "'" ]
		stdoutCapture = [ 'stdout' ]
		stderrCapture = [ 'stderr' ]
		result = self.__Exec(query, stdoutCapture, stderrCapture)
		if result == XyResult.Ok and self.__ValidCapture(stdoutCapture):
			lines = stdoutCapture[1].split(os.linesep)
			for line in lines:
				if line:
					files_.append(preamble_ + line)
					# XyLog.Debug(line)
		return result


	def RevisionFilesOnly(self, files_, id_, preamble_='', branch_=None):
		if branch_ is None:
			branch_ = self.Branch()

		# Complex queries need special formatting or get chewed up by Windows shell.
		query = ['find', 'revision', 'where', "branch='"+branch_+"'",
			'and', 'changeset='+str(id_),
			'--format={type}#{path}', '--nototal', 'on', 'repositories', "'" + self.__repo + "'" ]
		stdoutCapture = [ 'stdout' ]
		stderrCapture = [ 'stderr' ]
		result = self.__Exec(query, stdoutCapture, stderrCapture)
		if result == XyResult.Ok and self.__ValidCapture(stdoutCapture):
			lines = stdoutCapture[1].split(os.linesep)
			for line in lines:
				item = line.split('#')
				# Filter out directories from changelist.
				if line and len(item) > 1 and item[0] != 'dir' and item[1]:
					files_.append(preamble_ + item[1])
					# XyLog.Debug(line)
		return result


	def Update(self, path_=None):
		if path_ is None:
			path_ = self.__root
		query = ['update', path_]
		result = self.__Exec(query)
		return result


class PlasticPoller(base.PollingChangeSource, StateMixin):
	"""This source will poll a remote git repo for changes and submit
	them to the change master."""

	compare_attrs = ["repourl", "branches", "workdir",
		"pollInterval", "cmbin", "usetimestamps",
		"category", "project", "pollAtLaunch"]

	def __init__(self, repourl, branches=None, branch=None,
		workdir=None, pollInterval=10 * 60,
		cmbin='cm', usetimestamps=True,
		category=None, project=None,
		pollinterval=-2, fetch_refspec=None,
		encoding='utf-8', pollAtLaunch=False, tzAdjust=7):

		# for backward compatibility; the parameter used to be spelled with 'i'
		if pollinterval != -2:
			pollInterval = pollinterval

		base.PollingChangeSource.__init__(self, name=repourl,
			pollInterval=pollInterval,
			pollAtLaunch=pollAtLaunch)

		if project is None:
			project = ''

		if branch and branches:
			config.error("PlasticPoller: can't specify both branch and branches")
		elif branch:
			branches = [branch]
		elif not branches:
			branches = ['main']

		self.repourl = repourl
		self.repo = repourl #.split(':')[0]
		self.branches = branches
		self.encoding = encoding
		# This is too complex for twisted and requires user interaction ( no fucking joke ), so
		# we need to call into another script to handle all this as twisted can not or should not.
		# self.cmbin = cmbin
		self.cmbin = '/usr/bin/python'
		self.cmscript = '/home/thendrix/Work/PaddleCreekGames/pcg-buildbot/master2/XyPlasticScmUtil.py'
		self.workdir = workdir
		self.usetimestamps = usetimestamps
		self.category = category
		self.project = project
		self.changeCount = 0
		self.lastRev = {}
		self.lastChangeSetId = {}
		self.tzAdjust = tzAdjust

		if fetch_refspec is not None:
			config.error("PlasticPoller: fetch_refspec is no longer supported. "
				"Instead, only the given branches are downloaded.")

		if self.workdir is None:
			self.workdir = 'PlasticPoller-work'
			

	@defer.inlineCallbacks
	def _process_changes(self, newRev, branch):
		"""
		Read changes since last change.

		- Read list of commit hashes.
		- Extract details from each commit.
		- Add changes to database.
		"""

		# initial run, don't parse all history
		if not self.lastRev:
			return
		if newRev in self.lastRev.values():
			# TODO: no new changes on this branch
			# should we just use the lastRev again, but with a different branch?
			pass

		# get the change list
		revListArgs = ([r'--format=%H', r'%s' % newRev] +
			[r'^%s' % rev for rev in self.lastRev.values()] +
			[r'--'])
		self.changeCount = 0
		results = yield self._dovccmd('log', revListArgs, path=self.workdir)

		# process oldest change first
		revList = results.split()
		revList.reverse()
		self.changeCount = len(revList)
		self.lastRev[branch] = newRev

		log.msg('PlasticPoller: processing %d changes: %s from "%s"'
			% (self.changeCount, revList, self.repourl))

		for rev in revList:
			dl = defer.DeferredList([
				self._get_commit_timestamp(rev),
				self._get_commit_author(rev),
				self._get_commit_files(rev),
				self._get_commit_comments(rev),
			], consumeErrors=True)

			results = yield dl

			# check for failures
			failures = [r[1] for r in results if not r[0]]
			if failures:
				# just fail on the first error; they're probably all related!
				raise failures[0]

			timestamp, author, files, comments = [r[1] for r in results]
			yield self.master.addChange(
				author=author,
				revision=rev,
				files=files,
				comments=comments,
				when_timestamp=epoch2datetime(timestamp),
				branch=self._removeHeads(branch),
				category=self.category,
				project=self.project,
				repository=self.repourl
				# ,src='plasticscm'
				)

	def startService(self):
		# make our workdir absolute, relative to the master's basedir
		if not os.path.isabs(self.workdir):
			self.workdir = os.path.join(self.master.basedir, self.workdir)
			log.msg("PlasticPoller: using workdir '%s'" % self.workdir)

		d = self.getState('lastRev', {})

		def setLastRev(lastRev):
			self.lastRev = lastRev
		d.addCallback(setLastRev)

		d.addCallback(lambda _:
					  base.PollingChangeSource.startService(self))
		d.addErrback(log.err, 'while initializing PlasticPoller repository')

		return d

	def describe(self):
		str = ('PlasticPoller watching the remote repository ' + self.repo)

		if self.branches:
			if self.branches is True:
				str += ', branches: ALL'
			elif not callable(self.branches):
				str += ', branches: ' + ', '.join(self.branches)

		if not self.master:
			str += " [STOPPED - check log]"

		return str

	@defer.inlineCallbacks
	def poll(self):
		branches = self.branches
		if branches is True or callable(branches):
			branches = []
			## @todo YEILD and handle result.
			# result = scm.Changes(branches)

		# We haven't got a changeset for this branch before
		# if self.lastChangeSetId is None:

		revs = {}
		for branch in branches:
			scm = XyPlasticScm('/tmp', repo_=self.repo, branch_=branch)

			# Start at -1 to catch 0th commit for new branches.
			id = -1
			try:
				if self.lastChangeSetId[branch]:
					id = int( self.lastChangeSetId[branch] )

			except:
				# If we do NOT have a previous changesetid then set latest to avoid full iteration
				# Replace value[0] with None to force stress test iteration of ALL changesets
				log.msg('== QUERY == LastChangesetId(); Init fallback')
				id = scm.LastChangesetId()
				self.lastChangeSetId[branch] = id
				log.msg('== RESULT == Init fallback: ' + str(id) )

			# The server was just reset or reconfigured OR... plastic query timed out!
			# If there is a plastic timeout just keep id as -1 and let next poll try again.
			if id < 0:
				# No working 'last' revision found, so retry to handle network errors.
				log.msg('== QUERY == LastChangesetId(); Handle invalid id')
				id = scm.LastChangesetId()
				log.msg('== RESULT == Handle invalid id: '+ str(id) )

			# There was a 'last' revision found, so filter all new changesets since then...
			else:
				changeset = []
				result = scm.ChangesAfter(changeset, id)

				if changeset and changeset[0]:
					log.msg('repo : ' + self.repo)
					log.msg('branch : ' + branch)

					lastChange = None
					for change in changeset:
						# Filter out empty changes
						if change and change[0]:
							log.msg('changeset : ' + str(change))

							# Save as a tuple to avoid parsing a string.
							revs[branch] = change

							lid = int( change[0] )
							if lid > id:
								id = lid

							filesChanged = []
							scm.RevisionFilesOnly(filesChanged, id, '/'+self.repo+'/'+branch)

							# No files? Lookup possible merge as plastic requires dependent query for that.
							if not filesChanged:
								result = []
								scm.LookupMergeId(branch, id, result)
								log.msg('merge:'+str(result))

								# If merge lookup revision history from parent branch to get files
								if len(result) > 1:
									ok = scm.RevisionFilesOnly(filesChanged, result[2], '', result[1])

							when = datetime.datetime.strptime(change[3], '%m/%d/%Y %I:%M:%S %p')

							# Quick in-place TZ conversion ( DST likely won't work unless proped from scm )
							from_zone = tz.tzutc()
							when = when.replace(tzinfo=from_zone)
							when += datetime.timedelta(hours=self.tzAdjust)
							# to_zone = tz.tzlocal()
							# when = utc.astimezone(to_zone)

							yield self.master.addChange(
								author=change[2],
								revision=change[1],
								files=filesChanged,
								comments=change[4],
								when_timestamp=when,
								branch=branch,
								category=self.category,
								project=self.project,
								repository=self.repourl
								# ,src='plasticscm'
								)

							lastChange = change

			# Bookkeeping
			if self.lastChangeSetId[branch] is None or int(self.lastChangeSetId[branch]) < id:
				log.msg('last-changeset-id : ' + str(id) )
				self.lastChangeSetId[branch] = id

		# Merge dictionaries
		self.lastRev.update(revs)
		yield self.setState('lastRev', self.lastRev)

