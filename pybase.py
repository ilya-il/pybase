#!/usr/bin/python3
# coding: utf-8

"""
    Base python application
"""

import maildata
import oradata

import argparse
import ctypes
import email
import logging
import logging.handlers
import os
import smtplib
import sys
import traceback

from configparser import ConfigParser
from functools import wraps
from datetime import datetime

global cx_Oracle


class App(object):
    def __init__(self):
        """Constructor"""
        # program path
        self.program_dir = os.path.dirname(os.path.realpath(__file__))
        # program start dir
        self.start_dir = os.getcwd()
        # program file name
        self.program_file = os.path.basename(__file__)
        # config file name
        self.config_file = os.path.splitext(self.program_file)[0] + '.ini'
        # Oracle
        self.ora_con = None
        self.ora_select_cur = None
        self.ora_update_cur = None

        # check user is root/admin
        self.check_admin()

        # read config
        self.cfg = ConfigParser()
        self.cfg.read(os.path.join(self.program_dir, self.config_file), encoding='utf-8')

        # create argparse
        self.args = self.__create_args()
        # create logger
        self.logger = self.__create_logger()

        # log program start
        self.logger.info('Start {0}'.format(self.cfg['main']['program']))
        self.logger.info('Command line - {0}'.format(sys.argv))

    def __del__(self):
        """Destructor"""
        pass

    def run(self):
        """Run program"""
        try:
            if self.args.command == 'cmd1':  # simple function with no argument
                self.cmd1()
            elif self.args.command == 'cmd2':  # simple function with one argument
                self.cmd2()
            elif self.args.command == 'cmd3':  # simple function to deal with Oracle
                self.oracle_connect()
                self.cmd3()
                self.oracle_disconnect()
            else:
                print('Command not supported')
        except Exception as e:
            self.logger.exception('EXCEPTION - ' + str(e))
            subject = 'EXCEPTION - {0}'.format(self.cfg['main']['program'])
            text = maildata.NOTIFY_TEXT.format(
                from_name=self.cfg['main']['program'],
                subject='EXCEPTION',
                text='{0}.'.format(traceback.format_exc())
            )
            self.send_mail(
                mail_host=self.cfg['email']['mail_host'],
                email_from=self.cfg['email']['sender_mail'],
                email_to=self.cfg['email']['sender_mail'],
                subject=subject,
                message=text,
                priority='1'
            )

    # ------------- Init functions -------------

    @staticmethod
    def __create_args():
        """Create argparser"""
        parser = argparse.ArgumentParser(description='Base python application')
        # optional arguments
        parser.add_argument('-d', '--debug', action='store_true', dest='debug', default=False,
                            help='Create debug log')
        # command parsers
        subparsers = parser.add_subparsers(title='Command list', dest='command', metavar='command')
        subparsers.required = True

        subparsers.add_parser('cmd1', help='Simple command with no arguments')
        cmd2 = subparsers.add_parser('cmd2', help='Simple command with one argument')
        cmd2.add_argument('cmd2_arg1', type=str, help='CMD2 required argument')
        subparsers.add_parser('cmd3', help='Simple command to deal with Oracle')

        # positional arguments
        parser.add_argument('pos_arg', type=str, help="Posisional argument")

        return parser.parse_args()

    def __create_logger(self):
        """Create logger"""
        timestamp = datetime.now().strftime('%Y%m%d-%H%M%S%f')

        logger = logging.getLogger('main')
        if self.args.debug:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)

        file_fmt = logging.Formatter(u'[%(asctime)s] %(levelname)-8s %(message)s')
        dbg_fmt = logging.Formatter(u'[%(asctime)s] %(levelname)-8s %(message)s')
        std_fmt = logging.Formatter(u'%(message)s')

        # console logging
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(std_fmt)
        handler.setLevel(logging.INFO)
        logger.addHandler(handler)

        # standard log
        handler = logging.FileHandler(os.path.join(self.cfg['main']['log_dir'],
                                                   'info-{0}.log'.format(timestamp)),
                                      'a')
        handler.setFormatter(file_fmt)
        handler.setLevel(logging.INFO)
        logger.addHandler(handler)

        # syslog
        if self.cfg['syslog']['syslog_enable'] == 'Y':
            syslog_fmt = logging.Formatter(u'{p}: %(message)s'.format(p=self.cfg['syslog']['syslog_pname']))
            handler = logging.handlers.SysLogHandler(address=(self.cfg['syslog']['syslog_server'], 514))
            handler.setFormatter(syslog_fmt)
            handler.setLevel(logging.INFO)
            logger.addHandler(handler)

        # debug log
        if self.args.debug:
            handler = logging.FileHandler(os.path.join(self.cfg['main']['log_dir'],
                                                       'debug-{0}.log'.format(timestamp)),
                                          'a')
            handler.setFormatter(dbg_fmt)
            handler.setLevel(logging.DEBUG)
            logger.addHandler(handler)

        return logger

    # ------------- Utils functions -------------

    def timer_decorator(func):
        """Timer decorator

        Decorator example from here - https://stackoverflow.com/questions/1263451/python-decorators-in-classes
        """

        @wraps(func)
        def wrapper(self, *args, **kwargs):
            t1 = datetime.now()
            res = func(self, *args, **kwargs)
            t2 = datetime.now()
            self.logger.info('Time elapsed (sec): {0}'.format((t2 - t1).total_seconds()))

            return res
        return wrapper

    @staticmethod
    def send_mail(mail_host, email_from, email_to, subject, message, priority='3'):
        """Send email over SMTP mailserver:25
        :param mail_host: mail host, ex: mymailserver.com
        :param email_from: sender's email, ex: sender@mymailserver.com
        :param email_to: to email, may be several over ',', ex: john@gmail.com, mary@yahoo.com
        :param subject: email subject
        :param message: email text
        """
        s = smtplib.SMTP(mail_host)
        msg = email.message.EmailMessage()

        msg['Subject'] = subject
        msg['From'] = email_from
        msg['To'] = email_to
        msg['X-Priority'] = priority
        msg.set_content(message)

        s.send_message(msg)

    @staticmethod
    def check_admin():
        """Check user for admin/root rights"""
        if os.name == 'nt':
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
        else:
            is_admin = os.getuid() == 0

        if is_admin:
            raise RuntimeError('Error! User has admin/root rights!')

    # ------------- Oracle functions -------------

    def oracle_decorator(func):
        """Decorator to check and set up Oracle enviroment

            If env OK: import cx_Oracle module and run decorated function
            If env in not OK: set enviroment and restart program with the same parameters -
                on next run we'll get into OK way

            Way 1: We have Oracle Instant Client path in config file.
                var 1: OIC is already in PATH/LD_LIBRARY_PATH - all's OK, import cx_Oracle, run function
                var 2: OIC is not is PATH/LD_LIBRARY_PATH - add OIC in PATH/LD_LIBRARY_PATH and restart program
                       with same command line

            Way 2: We have no Oracle Instant Client path in config file.
                So Oracle enviroment must be already set in the system - God bless DBA!
        """

        @wraps(func)
        def wrapper(self, *args, **kwargs):
            ora_client_path = self.cfg['oracle']['ic_path']

            ora_check = ora_client_path == '' or \
                (os.name == 'nt' and os.environ.get('PATH') and os.environ.get('PATH').find(
                       ora_client_path) != -1) or \
                (os.name == 'posix' and os.environ.get('LD_LIBRARY_PATH') and os.environ.get('LD_LIBRARY_PATH').find(
                       ora_client_path) != -1)

            if ora_check:
                # This is dirty trick for import cx_Oracle
                # To have dynamic import for cx_Oracle use global и __import__
                # https://docs.python.org/3.6/reference/simple_stmts.html#the-global-statement
                # https://docs.python.org/3.6/library/functions.html#__import__
                global cx_Oracle
                cx_Oracle = __import__('cx_Oracle', globals(), locals())

                return func(self, *args, **kwargs)
            else:
                # check OS-system
                # set PATH/LD_LIBRARY_PATH
                # restart ourself
                if os.name == 'nt':
                    if os.environ.get('PATH'):
                        os.environ['PATH'] += ';' + ora_client_path
                    else:
                        os.environ['PATH'] = ora_client_path
                    # under Windows we must use python executable file as first parameter
                    os.execv(sys.executable, [sys.executable, ] + sys.argv)
                else:
                    if os.environ.get('LD_LIBRARY_PATH'):
                        os.environ['LD_LIBRARY_PATH'] += ';' + ora_client_path
                    else:
                        os.environ['LD_LIBRARY_PATH'] = ora_client_path
                    os.execv(sys.argv[0], sys.argv)

        return wrapper

    @oracle_decorator
    def oracle_connect(self):
        """Oracle connect"""
        self.logger.info('Init Oracle. Database - {0}@{1}/{2}'.
                         format(self.cfg['oracle']['login'],
                                self.cfg['oracle']['host'],
                                self.cfg['oracle']['sid']))

        ora_con = cx_Oracle.connect('{u}/{p}@{h}/{s}'.format(u=self.cfg['oracle']['login'],
                                                             p=self.cfg['oracle']['password'],
                                                             h=self.cfg['oracle']['host'],
                                                             s=self.cfg['oracle']['sid']),
                                    encoding='UTF-8')
        ora_select_cur = ora_con.cursor()
        ora_update_cur = ora_con.cursor()

        self.ora_con, self.ora_select_cur, self.ora_update_cur = ora_con, ora_select_cur, ora_update_cur

    def oracle_disconnect(self, commit=False):
        """Oracle disconnect"""
        if commit:
            self.ora_con.commit()

        self.ora_update_cur.close()
        self.ora_select_cur.close()
        self.ora_con.close()

    @staticmethod
    def oracle_row_factory(cursor):
        """Function to handle values, returned by SELECT

        :param cursor:
        :return:

        By default cursor.fetch() returns list(), and list() doesn't have
        column names. So we need to transform list() to dict().

        'column_names' is taken from cursor. lower() is required, because all the 'description' is uppercase.
        'args' is a returned list() from SELECT. We need to translate NULL-values to empty strings

           https://stackoverflow.com/questions/35045879/cx-oracle-how-can-i-receive-each-row-as-a-dictionary
           https://stackoverflow.com/questions/53249527/how-does-cursor-rowfactory-cx-oracle-work-in-returning-each-row-in-dictionary
           https://github.com/oracle/python-cx_Oracle/blob/master/samples/GenericRowFactory.py
        """
        column_names = [d[0].lower() for d in cursor.description]

        def create_row(*args):
            return dict(zip(column_names,
                            [a if a is not None else '' for a in args]))

        return create_row

    # ------------- Main functions -------------

    def cmd1(self):
        self.logger.info('>>>>> Begin cmd1() <<<<<')

        print('Hello cmd1! Positional argument - {0}'.format(self.args.pos_arg))

        self.logger.info('>>>>> End cmd1() <<<<<')

    @timer_decorator
    def cmd2(self):
        self.logger.info('>>>>> Begin cmd2() <<<<<')

        print('Hello cmd2! Cmd2 arg - {0}. Positional argument - {1}'.format(self.args.cmd2_arg1, self.args.pos_arg))
        print('See time elapsed!')

        self.logger.info('>>>>> End cmd2() <<<<<')

    def cmd3(self):
        self.logger.info('>>>>> Begin cmd3() <<<<<')

        self.ora_select_cur.execute(oradata.ORA_SELECT_FROM_DUAL_SQL)
        # set rowfactory AFTER(!) cursor.execute(), but BEFORE cursor.fetch()
        self.ora_select_cur.rowfactory = App.oracle_row_factory(self.ora_select_cur)

        res = self.ora_select_cur.fetchone()

        if 'column1' in res:
            print('Test Oracle - OK')
        else:
            print('Test Oracle - ERROR')

        self.logger.info('>>>>> End cmd3() <<<<<')

    # ------------- SET UP decorators (after all functions) -------------

    timer_decorator = staticmethod(timer_decorator)
    oracle_decorator = staticmethod(oracle_decorator)

# ======================================================================================================================


if __name__ == '__main__':
    app = App()
    app.run()
