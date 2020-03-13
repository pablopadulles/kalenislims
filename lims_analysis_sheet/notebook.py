# This file is part of lims_analysis_sheet module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.

from trytond.model import ModelSQL, ModelView, fields
from trytond.wizard import Wizard, StateTransition, StateView, Button
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval
from trytond.transaction import Transaction
from trytond.modules.lims.formula_parser import FormulaParser

__all__ = ['NotebookLine', 'AddFractionControlStart', 'AddFractionControl',
    'RepeatAnalysisStart', 'RepeatAnalysisStartLine', 'RepeatAnalysis',
    'InternalRelationsCalc']


class NotebookLine(metaclass=PoolMeta):
    __name__ = 'lims.notebook.line'

    def get_analysis_sheet_template(self):
        cursor = Transaction().connection.cursor()
        TemplateAnalysis = Pool().get('lims.template.analysis_sheet.analysis')

        cursor.execute('SELECT template '
            'FROM "' + TemplateAnalysis._table + '" '
            'WHERE analysis = %s '
            'AND (method = %s OR method IS NULL)',
            (self.analysis.id, self.method.id))
        template = cursor.fetchone()
        return template and template[0] or None


class AddFractionControlStart(ModelView):
    'Add Fraction Control'
    __name__ = 'lims.analysis_sheet.add_fraction_con.start'

    original_fraction = fields.Many2One('lims.fraction', 'Fraction',
        required=True, domain=[('id', 'in', Eval('fraction_domain'))],
        depends=['fraction_domain'])
    fraction_domain = fields.Many2Many('lims.fraction', None, None,
        'Fraction domain')


class AddFractionControl(Wizard):
    'Add Fraction Control'
    __name__ = 'lims.analysis_sheet.add_fraction_con'

    start_state = 'check'
    check = StateTransition()
    start = StateView('lims.analysis_sheet.add_fraction_con.start',
        'lims_analysis_sheet.analysis_sheet_add_fraction_con_start_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Add', 'add', 'tryton-ok', default=True),
            ])
    add = StateTransition()

    def transition_check(self):
        pool = Pool()
        AnalysisSheet = pool.get('lims.analysis_sheet')

        sheet_id = Transaction().context['active_id']
        sheet = AnalysisSheet(sheet_id)

        if sheet.state in ('active', 'validated'):
            return 'start'
        return 'end'

    def default_start(self, fields):
        cursor = Transaction().connection.cursor()
        pool = Pool()
        AnalysisSheet = pool.get('lims.analysis_sheet')
        Analysis = pool.get('lims.analysis')
        Fraction = pool.get('lims.fraction')
        NotebookLine = pool.get('lims.notebook.line')
        Notebook = pool.get('lims.notebook')

        defaults = {
            'fraction_domain': [],
            }

        sheet_id = Transaction().context['active_id']
        sheet = AnalysisSheet(sheet_id)

        t_analysis_ids = []
        for t_analysis in sheet.template.analysis:
            if t_analysis.analysis.type == 'analysis':
                t_analysis_ids.append(t_analysis.analysis.id)
            else:
                t_analysis_ids.extend(
                    Analysis.get_included_analysis_analysis(
                        t_analysis.analysis.id))

        stored_fractions_ids = Fraction.get_stored_fractions()

        notebook_lines = NotebookLine.search([
            ('notebook.fraction.special_type', '=', 'con'),
            ('notebook.fraction.id', 'in', stored_fractions_ids),
            ('analysis', 'in', t_analysis_ids),
            ('result', 'in', (None, '')),
            ('end_date', '=', None),
            ('annulment_date', '=', None),
            ])
        if notebook_lines:
            notebook_lines_ids = ', '.join(str(nl.id) for nl in notebook_lines)
            cursor.execute('SELECT DISTINCT(n.fraction) '
                'FROM "' + Notebook._table + '" n '
                    'INNER JOIN "' + NotebookLine._table + '" nl '
                    'ON nl.notebook = n.id '
                'WHERE nl.id IN (' + notebook_lines_ids + ')')
            defaults['fraction_domain'] = [x[0] for x in cursor.fetchall()]

        return defaults

    def transition_add(self):
        pool = Pool()
        AnalysisSheet = pool.get('lims.analysis_sheet')
        Analysis = pool.get('lims.analysis')
        NotebookLine = pool.get('lims.notebook.line')

        sheet_id = Transaction().context['active_id']
        sheet = AnalysisSheet(sheet_id)

        t_analysis_ids = []
        for t_analysis in sheet.template.analysis:
            if t_analysis.analysis.type == 'analysis':
                t_analysis_ids.append(t_analysis.analysis.id)
            else:
                t_analysis_ids.extend(
                    Analysis.get_included_analysis_analysis(
                        t_analysis.analysis.id))

        clause = [
            ('notebook.fraction.id', '=', self.start.original_fraction.id),
            ('analysis', 'in', t_analysis_ids),
            ('result', 'in', (None, '')),
            ('end_date', '=', None),
            ('annulment_date', '=', None),
            ]
        notebook_lines = NotebookLine.search(clause)
        if notebook_lines:
            sheet.create_lines(notebook_lines)
        return 'end'


class RepeatAnalysisStart(ModelView):
    'Repeat Analysis'
    __name__ = 'lims.analysis_sheet.repeat_analysis.start'

    lines = fields.Many2Many(
        'lims.analysis_sheet.repeat_analysis.start.line', None, None,
        'Lines', required=True, domain=[('id', 'in', Eval('lines_domain'))],
        depends=['lines_domain'])
    lines_domain = fields.One2Many(
        'lims.analysis_sheet.repeat_analysis.start.line', None,
        'Lines domain')


class RepeatAnalysisStartLine(ModelSQL, ModelView):
    'Analysis Sheet Line'
    __name__ = 'lims.analysis_sheet.repeat_analysis.start.line'

    line = fields.Many2One('lims.notebook.line', 'Line')
    fraction = fields.Function(fields.Many2One('lims.fraction', 'Fraction'),
        'get_line_field', searcher='search_line_field')
    analysis = fields.Function(fields.Many2One('lims.analysis', 'Analysis'),
        'get_line_field', searcher='search_line_field')
    repetition = fields.Function(fields.Integer('Repetition'),
        'get_line_field', searcher='search_line_field')
    session_id = fields.Integer('Session ID')

    @classmethod
    def __register__(cls, module_name):
        super(RepeatAnalysisStartLine, cls).__register__(module_name)
        cursor = Transaction().connection.cursor()
        cursor.execute('DELETE FROM "' + cls._table + '"')

    @classmethod
    def __setup__(cls):
        super(RepeatAnalysisStartLine, cls).__setup__()
        cls._order.insert(0, ('fraction', 'ASC'))
        cls._order.insert(1, ('analysis', 'ASC'))
        cls._order.insert(2, ('repetition', 'ASC'))

    @classmethod
    def get_line_field(cls, lines, names):
        result = {}
        for name in names:
            result[name] = {}
            if name in ('fraction', 'analysis'):
                for l in lines:
                    field = getattr(l.line, name, None)
                    result[name][l.id] = field.id if field else None
            else:
                for l in lines:
                    result[name][l.id] = getattr(l.line, name, None)
        return result

    @classmethod
    def search_line_field(cls, name, clause):
        return [('line.' + name,) + tuple(clause[1:])]


class RepeatAnalysis(Wizard):
    'Repeat Analysis'
    __name__ = 'lims.analysis_sheet.repeat_analysis'

    start_state = 'check'
    check = StateTransition()
    start = StateView('lims.analysis_sheet.repeat_analysis.start',
        'lims_analysis_sheet.analysis_sheet_repeat_analysis_start_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Repeat', 'repeat', 'tryton-ok', default=True),
            ])
    repeat = StateTransition()

    def transition_check(self):
        pool = Pool()
        AnalysisSheet = pool.get('lims.analysis_sheet')

        sheet_id = Transaction().context['active_id']
        sheet = AnalysisSheet(sheet_id)

        if sheet.state in ('active', 'validated'):
            return 'start'
        return 'end'

    def default_start(self, fields):
        pool = Pool()
        AnalysisSheet = pool.get('lims.analysis_sheet')
        Data = pool.get('lims.interface.data')
        RepeatAnalysisStartLine = pool.get(
            'lims.analysis_sheet.repeat_analysis.start.line')

        defaults = {}

        sheet_id = Transaction().context['active_id']
        sheet = AnalysisSheet(sheet_id)

        nl_field = (sheet.template.interface.notebook_line_field and
            sheet.template.interface.notebook_line_field.alias or None)
        if not nl_field:
            return defaults

        to_create = []
        with Transaction().set_context(
                lims_interface_table=sheet.compilation.table.id):
            lines = Data.search([('compilation', '=', sheet.compilation.id)])
            for line in lines:
                nl = getattr(line, nl_field)
                if not nl:
                    continue
                to_create.append({
                    'session_id': self._session_id,
                    'line': nl,
                    })
        lines = RepeatAnalysisStartLine.create(to_create)
        defaults['lines_domain'] = [l.id for l in lines]
        return defaults

    def transition_repeat(self):
        pool = Pool()
        AnalysisSheet = pool.get('lims.analysis_sheet')
        NotebookLine = pool.get('lims.notebook.line')
        #EntryDetailAnalysis = pool.get('lims.entry.detail.analysis')

        sheet_id = Transaction().context['active_id']
        sheet = AnalysisSheet(sheet_id)

        to_create = []
        #details_to_update = []

        for sheet_line in self.start.lines:
            nline_to_repeat = sheet_line.line
            detail_id = nline_to_repeat.analysis_detail.id
            defaults = {
                'notebook': nline_to_repeat.notebook.id,
                'analysis_detail': detail_id,
                'service': nline_to_repeat.service.id,
                'analysis': nline_to_repeat.analysis.id,
                'analysis_origin': nline_to_repeat.analysis_origin,
                'repetition': nline_to_repeat.repetition + 1,
                'laboratory': nline_to_repeat.laboratory.id,
                'method': nline_to_repeat.method.id,
                'device': (nline_to_repeat.device.id if nline_to_repeat.device
                    else None),
                'initial_concentration': nline_to_repeat.initial_concentration,
                'decimals': nline_to_repeat.decimals,
                'report': nline_to_repeat.report,
                'concentration_level': (nline_to_repeat.concentration_level.id
                    if nline_to_repeat.concentration_level else None),
                'results_estimated_waiting': (
                    nline_to_repeat.results_estimated_waiting),
                'department': nline_to_repeat.department,
                'final_concentration': nline_to_repeat.final_concentration,
                'initial_unit': (nline_to_repeat.initial_unit.id if
                    nline_to_repeat.initial_unit else None),
                'final_unit': (nline_to_repeat.final_unit.id if
                    nline_to_repeat.final_unit else None),
                'detection_limit': nline_to_repeat.detection_limit,
                'quantification_limit': nline_to_repeat.quantification_limit,
                }
            to_create.append(defaults)
            #details_to_update.append(detail_id)

        notebook_lines = NotebookLine.create(to_create)
        if notebook_lines:
            sheet.create_lines(notebook_lines)

        #details = EntryDetailAnalysis.search([
            #('id', 'in', details_to_update),
            #])
        #if details:
            #EntryDetailAnalysis.write(details, {
                #'state': 'unplanned',
                #})

        return 'end'


class InternalRelationsCalc(Wizard):
    'Internal Relations Calculation'
    __name__ = 'lims.analysis_sheet.internal_relations_calc'

    start_state = 'check'
    check = StateTransition()
    calcuate = StateTransition()

    def transition_check(self):
        AnalysisSheet = Pool().get('lims.analysis_sheet')

        sheet_id = Transaction().context['active_id']
        sheet = AnalysisSheet(sheet_id)

        if sheet.state in ('active', 'validated'):
            return 'calcuate'

        return 'end'

    def transition_calcuate(self):
        pool = Pool()
        AnalysisSheet = pool.get('lims.analysis_sheet')
        ModelField = pool.get('ir.model.field')
        Column = pool.get('lims.interface.column')
        Data = pool.get('lims.interface.data')

        sheet_id = Transaction().context['active_id']
        sheet = AnalysisSheet(sheet_id)

        nl_field = (sheet.template.interface.notebook_line_field and
            sheet.template.interface.notebook_line_field.alias or None)
        if not nl_field:
            return 'end'

        nl_result_field, = ModelField.search([
            ('model.model', '=', 'lims.notebook.line'),
            ('name', '=', 'result'),
            ])
        result_column = Column.search([
            ('interface', '=', sheet.template.interface),
            ('transfer_field', '=', True),
            ('related_line_field', '=', nl_result_field)
            ])
        if not result_column:
            return 'end'

        result_field = result_column[0].alias
        relations = {}
        notebooks = {}
        with Transaction().set_context(
                lims_interface_table=sheet.compilation.table.id):
            lines = Data.search([('compilation', '=', sheet.compilation.id)])
            for line in lines:
                notebook_line = getattr(line, nl_field)
                if not notebook_line:
                    continue
                if notebook_line.notebook.id not in notebooks:
                    notebooks[notebook_line.notebook.id] = {}
                notebooks[notebook_line.notebook.id][
                    notebook_line.analysis.code] = getattr(line, result_field)
                if notebook_line.analysis.behavior == 'internal_relation':
                    relations[line] = notebook_line

            if not relations:
                return 'end'

            for s_line, n_line in relations.items():
                result = self._get_relation_result(n_line.analysis.code,
                    notebooks[n_line.notebook.id])
                if result is not None:
                    s_line.set_result(str(result), result_field)

        return 'end'

    def _get_relation_result(self, analysis_code, vars, round_=False):
        pool = Pool()
        Analysis = pool.get('lims.analysis')

        internal_relations = Analysis.search([
            ('code', '=', analysis_code),
            ])
        if not internal_relations:
            return None
        formula = internal_relations[0].result_formula
        if not formula:
            return None
        for i in (' ', '\t', '\n', '\r'):
            formula = formula.replace(i, '')
        variables = self._get_variables(formula, vars)
        if not variables:
            return None

        parser = FormulaParser(formula, variables)
        value = parser.getValue()

        if int(value) == value:
            res = int(value)
        else:
            epsilon = 0.0000000001
            if int(value + epsilon) != int(value):
                res = int(value + epsilon)
            elif int(value - epsilon) != int(value):
                res = int(value)
            else:
                res = float(value)
        if not round_:
            return res
        decimals = 4
        return round(res, decimals)

    def _get_analysis_result(self, analysis_code, vars):
        try:
            res = float(vars[analysis_code])
        except (TypeError, ValueError):
            return None
        decimals = 4
        return round(res, decimals)

    def _get_variables(self, formula, vars):
        pool = Pool()
        VolumeConversion = pool.get('lims.volume.conversion')

        variables = {}
        for prefix in ('A', 'D', 'T', 'Y', 'R'):
            while True:
                idx = formula.find(prefix)
                if idx >= 0:
                    var = formula[idx:idx + 5]
                    variables[var] = None
                    formula = formula.replace(var, '_')
                else:
                    break
        for var in variables.keys():
            if var[0] == 'A':
                analysis_code = var[1:]
                result = self._get_analysis_result(analysis_code, vars)
                if result is not None:
                    variables[var] = result
            elif var[0] == 'D':
                analysis_code = var[1:]
                result = self._get_analysis_result(analysis_code, vars)
                if result is not None:
                    result = VolumeConversion.brixToDensity(result)
                    if result is not None:
                        variables[var] = result
            elif var[0] == 'T':
                analysis_code = var[1:]
                result = self._get_analysis_result(analysis_code, vars)
                if result is not None:
                    result = VolumeConversion.brixToSolubleSolids(result)
                    if result is not None:
                        variables[var] = result
            elif var[0] == 'R':
                analysis_code = var[1:]
                result = self._get_relation_result(analysis_code, vars,
                    round_=True)
                if result is not None:
                    result = VolumeConversion.brixToSolubleSolids(result)
                    if result is not None:
                        variables[var] = result
            elif var[0] == 'Y':
                analysis_code = var[1:]
                result = self._get_relation_result(analysis_code, vars,
                    round_=True)
                if result is not None:
                    result = VolumeConversion.brixToDensity(result)
                    if result is not None:
                        variables[var] = result
        for var in variables.values():
            if var is None:
                return None
        return variables
