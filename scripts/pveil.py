#!/usr/bin/env python
''' pveil.py - Add veiling glare to picture

Drop-in replacement for the original csh script by Greg Ward.
2016 - Georg Mischler
'''
__all__ = ('main')
import sys
import os
import re
import tempfile
import subprocess
import argparse

SHORTPROGN = os.path.splitext(os.path.split(sys.argv[0])[1])[0]
class Error(Exception): pass

CALFILE = b''' { generated by pveil.py }
N : I(0);
K : 9.2;	{ should be 9.6e-3/PI*(180/PI)^2 == 10.03 ? }
bound(a,x,b) : if(a-x, a, if(x-b, b, x));
Acos(x) : acos(bound(-1,x,1));
sq(x) : x*x;
mul(ct) : if(ct-cos(.5*PI/180), K/sq(.5), K/sq(180/PI)*ct/sq(Acos(ct)));
Dx1 = Dx(1); Dy1 = Dy(1); Dz1 = Dz(1);		{ minor optimization }
cosa(i) = SDx(i)*Dx1 + SDy(i)*Dy1 + SDz(i)*Dz1;
sum(i) = if(i-.5, mul(cosa(i))*I(i)+sum(i-1), 0);
veil = le(1)/WE * sum(N);
ro = ri(1) + veil;
go = gi(1) + veil;
bo = bi(1) + veil;
'''

class Pveil():
	def __init__(self, args):
		self.donothing = args.N
		self.verbose = args.V or self.donothing
		self.imgfile = args.picture[0][0]
		self.tmpfname = ''
		try: self.run()
		finally:
			if os.path.isfile(self.tmpfname):
				try: os.unlink(self.tmpfname)
				except OSError: pass

	def raise_on_error(self, actstr, e):
		raise Error('Unable to %s - %s' % (actstr, str(e)))

	def qjoin(self, sl):
		def _q(s):
			if ' ' in s or '\t' in s or ';' in s:
				return "'" + s + "'"
			return s
		return  ' '.join([_q(s) for s in sl])

	def run(self):
		fg_cmd = 'findglare -r 400 -c -p'.split() + [self.imgfile]
		p = self.call_one(fg_cmd, 'extract glare values', out=subprocess.PIPE)
		if self.donothing:
			fg_data = None
		else:
			fg_data = p.stdout.readlines()
		gv_table = self.extract_glarevals(fg_data)
		if not gv_table and not self.donothing:
			# use the file descriptor for bytes on Py3
			if self.verbose:
				sys.stderr.write('### no glare, send file unchanged\n')
			with open(self.imgfile, 'rb') as f:
				os.write(sys.stdout.fileno(), f.read())
				return
		if self.donothing:
			self.tmpfname = tempfile.mktemp()
			tmp_fd = None
		else:
			tmp_fd, self.tmpfname = tempfile.mkstemp()
		self.write_calfile(tmp_fd, gv_table)
		# XXX The original sends duplicates of some headers, no idea why.
		pc_cmd = ['pcomb', '-f', self.tmpfname, self.imgfile]
		self.call_one(pc_cmd, 'combine image')

	def write_calfile(self, cal_fd, gv_table):
		if self.verbose:
			sys.stderr.write('### write temp calfile "%s"\n' % self.tmpfname)
		if self.donothing: return
		sel_lists = zip(*gv_table)
		# mkstemp() gives us an os-level file, but we only have ASCII anyway
		for k,vals in zip((b'SDx',b'SDy',b'SDz',b'I'), sel_lists):
			os.write(cal_fd, k + b'(x):select(x,')
			os.write(cal_fd, b','.join(vals))
			os.write(cal_fd, b');\n')
		os.write(cal_fd, CALFILE)
		os.close(cal_fd)

	def extract_glarevals(self, lines):
		if self.donothing: return
		data = []
		found = False
		for line in lines:
			if found:
				if line.startswith(b'END glare source'):
					break
				items =  line.split()
				fsum = '%.6g'%(float(items[3])*float(items[4]))
				items = items[:3] +[fsum.encode('ascii')]
				data.append(items)
			elif line.startswith(b'BEGIN glare source'):
				found = True
		return data

	def call_one(self, cmdl, actstr, _in=None, out=None):
		if _in == subprocess.PIPE: stdin = _in
		elif _in: stdin = open(_in, 'rb')
		else: stdin = None
		if out == subprocess.PIPE: stdout = out
		elif out: stdout = open(out, 'wb')
		else: stdout = None
		displ = cmdl[:]
		if isinstance(_in, str): displ[:0] = [_in, '>']
		if isinstance(out, str): displ.extend(['>', out])
		if self.verbose:
			sys.stderr.write('### %s \n' % actstr)
			sys.stderr.write(self.qjoin(displ) + '\n')
		if not self.donothing:
			try: p = subprocess.Popen(cmdl, stdin=stdin, stdout=stdout)
			except Exception as e:
				self.raise_on_error(actstr, str(e))
			if stdin != subprocess.PIPE:
				# caller needs to wait after writing (else deadlock)
				res = p.wait()
				if res != 0:
					self.raise_on_error(actstr,
							'Nonzero exit (%d) from command [%s].'
							% (res, self.qjoin(displ)))
			return p


def main():
	''' This is a command line script and not currently usable as a module.
	Use the -H option for instructions.'''
	parser = argparse.ArgumentParser(add_help=False,
		description='Add veiling glare to picture')
	parser.add_argument('-N', action='store_true',
		help='Do nothing: dry-run (implies -V)')
	parser.add_argument('-V', action='store_true',
		help='Verbose: print commands to execute to stderr')
	parser.add_argument('-H', action='help',
		help='Help: print this text to stderr and exit')
	parser.add_argument('picture', action='append', nargs=1,
		help='HDR image files to analyze')
	Pveil(parser.parse_args())

if __name__ == '__main__':
	try: main()
	except KeyboardInterrupt:
		sys.stderr.write('*cancelled*\n')
	except Error as e:
		sys.stderr.write('%s: %s\n' % (SHORTPROGN, e))

