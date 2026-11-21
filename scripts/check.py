"""Check BPMN structure, key routes, C4 scope, and source/render consistency."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
NS = {'b': 'http://www.omg.org/spec/BPMN/20100524/MODEL',
      'd': 'http://www.omg.org/spec/BPMN/20100524/DI'}
BASES = ['01-process', '02-context', '03-containers', '04-ml-components']
MANIFEST = ROOT / 'diagrams/manifest.json'

def require(ok, message):
    if not ok:
        raise ValueError(message)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def validate_bpmn():
    root = ET.parse(ROOT / 'diagrams/01-process.bpmn').getroot()
    indexed = [e for e in root.iter() if e.get('id')]
    by_id = {e.get('id'): e for e in indexed}
    require(len(indexed) == len(by_id), 'BPMN: повторяющиеся ID.')
    process = root.find('b:process', NS)
    require(process is not None and process.get('isExecutable') == 'false', 'BPMN: ожидается описательная модель процесса.')
    participants = root.findall('b:collaboration/b:participant', NS)
    require(len(participants) == 2, 'BPMN: должны быть два пула.')
    lanes = process.findall('b:laneSet/b:lane', NS)
    require(len(lanes) == 3, 'BPMN: должны быть три дорожки.')
    node_kinds = {'startEvent', 'endEvent', 'exclusiveGateway', 'userTask', 'serviceTask', 'boundaryEvent'}
    nodes = {e.get('id'): e for e in process if e.tag.rsplit('}', 1)[-1] in node_kinds}
    lane_refs = [r.text for lane in lanes for r in lane.findall('b:flowNodeRef', NS)]
    require(set(lane_refs) == set(nodes) and len(lane_refs) == len(set(lane_refs)), 'BPMN: узел не отнесен к единственной дорожке.')
    adjacency = {id: [] for id in nodes}
    flows = {e.get('id'): e for e in process.findall('b:sequenceFlow', NS)}
    for id, flow in flows.items():
        source, target = flow.get('sourceRef'), flow.get('targetRef')
        require(source in nodes and target in nodes, f'{id}: поток вышел за границу процесса.')
        require('\\n' not in flow.get('name', ''), f'{id}: буквальный escape вместо переноса строки.')
        adjacency[source].append(target)
        require(id in [e.text for e in nodes[source].findall('b:outgoing', NS)], f'{id}: нет ссылки outgoing.')
        require(id in [e.text for e in nodes[target].findall('b:incoming', NS)], f'{id}: нет ссылки incoming.')
    for boundary in process.findall('b:boundaryEvent', NS):
        attached = boundary.get('attachedToRef')
        require(attached in nodes and boundary.get('cancelActivity') == 'true', 'BPMN: ошибка граничного события.')
        adjacency[attached].append(boundary.get('id'))
    for gateway in process.findall('b:exclusiveGateway', NS):
        if gateway.get('gatewayDirection') == 'Diverging':
            outgoing = gateway.findall('b:outgoing', NS)
            require(len(outgoing) == 2 and gateway.get('default') in flows, 'BPMN: неполная исключающая развилка.')
            for out in outgoing:
                if out.text != gateway.get('default'):
                    require(flows[out.text].find('b:conditionExpression', NS) is not None, 'BPMN: у ветки нет условия.')
    starts = process.findall('b:startEvent', NS)
    ends = process.findall('b:endEvent', NS)
    require(len(starts) == len(ends) == 1, 'BPMN: ожидается одно начало и один общий конец.')
    def reachable(start):
        seen, pending = set(), [start]
        while pending:
            current = pending.pop()
            if current not in seen:
                seen.add(current)
                pending.extend(adjacency[current])
        return seen
    require(reachable(starts[0].get('id')) == set(nodes), 'BPMN: есть недостижимые узлы.')
    require(all(ends[0].get('id') in reachable(n) for n in nodes), 'BPMN: найден тупиковый маршрут.')
    require('B04' not in reachable(flows['F_NoPermission'].get('targetRef')), 'Запрет замен не должен приводить к ML.')
    require(flows['F_ModelFailure'].get('targetRef') == 'B05', 'Ошибка ML должна вести к ручному выбору.')
    require(flows['F_LowScore'].get('targetRef') == 'B05', 'Низкий скор должен вести к ручному выбору.')
    require(flows['F_NoManualChoice'].get('targetRef') == 'B10', 'Отсутствие ручного выбора должно вести к контакту с покупателем.')
    require(flows['F_NoCandidates'].get('targetRef') == 'B10', 'Отсутствие аналогов должно вести к контакту с покупателем.')
    require(flows['F_Notified'].get('targetRef') == 'B08', 'После сообщения об отсутствии замены позиция удаляется.')
    require(flows['F_NotifyTimeout'].get('targetRef') == 'B08', 'Срок уведомления должен вести к удалению.')
    require(flows['F_NoAnswer'].get('targetRef') == 'B08', 'Истечение срока должно вести к удалению.')
    require(flows['F_StockConflict'].get('targetRef') == 'B08', 'Конфликт применения должен вести к удалению.')
    require(adjacency['B09'] == ['End'], 'Конечный результат должен проходить через запись исхода.')
    for message in root.findall('b:collaboration/b:messageFlow', NS):
        pair = {message.get('sourceRef'), message.get('targetRef')}
        require(pair in ({'B06','Participant_Customer'}, {'B10','Participant_Customer'}), 'BPMN: неожиданный обмен с внешним участником.')
    di_ids = {e.get('bpmnElement') for e in root.findall('.//d:BPMNShape', NS) + root.findall('.//d:BPMNEdge', NS)}
    require(set(nodes).union(flows) <= di_ids, 'BPMN: потеряны координаты элемента или связи.')
    require(all(x in nodes for x in (f'B{i:02d}' for i in range(1,11))), 'BPMN: пропущен бизнес-шаг.')
    return len(nodes), len(flows)

def validate_c4_and_files():
    context = (ROOT / 'diagrams/02-context.puml').read_text()
    containers = (ROOT / 'diagrams/03-containers.puml').read_text()
    components = (ROOT / 'diagrams/04-ml-components.puml').read_text()
    require(len(re.findall(r'^System\(', context, re.M)) == 1 and not re.search(r'^\s*Container(?:Db)?\(', context, re.M), 'C4 L1: смешаны уровни.')
    require(len(re.findall(r'^\s*Container(?:Db)?\(', containers, re.M)) == 6, 'C4 L2: ожидаются шесть контейнеров.')
    require(len(re.findall(r'^\s*Component\(', components, re.M)) == 6, 'C4 L3: ожидаются шесть компонентов.')
    require(not re.search(r'^\s*(?:Container|ContainerDb|System|System_Ext)\(', components, re.M), 'C4 L3: повторены другие контейнеры.')
    require('features_schema' in components and 'decision_id' in components, 'C4 L3: контракт отличается от README.')
    for text in (context,containers,components):
        require('legend' in text and 'title' in text, 'C4: нет заголовка или легенды.')
    readme = (ROOT / 'README.md').read_text()
    for link in re.findall(r'\]\(([^)]+)\)', readme):
        if not link.startswith(('http:', 'https:', '#')):
            require((ROOT / link).is_file(), f'README: отсутствует {link}.')
    return readme

def file_manifest():
    files = ['diagrams/01-process.bpmn', 'diagrams/style.puml', 'scripts/export_bpmn.py', 'scripts/render.sh']
    sizes = {}
    for base in BASES:
        files += [f'diagrams/{base}.{ext}' for ext in ('puml','svg','png')]
        png = (ROOT / f'diagrams/{base}.png').read_bytes()
        require(png.startswith(b'\x89PNG\r\n\x1a\n'), f'{base}.png: файл не является PNG.')
        w,h = struct.unpack('>II',png[16:24])
        require(w > 500 and h > 500, f'{base}: недостаточный размер изображения.')
        svg = ET.parse(ROOT / f'diagrams/{base}.svg').getroot()
        require(svg.tag.endswith('svg'), f'{base}.svg: неправильный формат.')
        sizes[base] = [w,h]
    return {'sources_and_renders': {p:sha(ROOT/p) for p in sorted(files)}, 'png_dimensions':sizes}

def main():
    args = argparse.ArgumentParser()
    args.add_argument('--record', action='store_true', help='Write fingerprints after successful rendering')
    opts = args.parse_args()
    counts = validate_bpmn()
    validate_c4_and_files()
    from export_bpmn import render
    before = (ROOT / 'diagrams/01-process.puml').read_bytes()
    # The exporter supports returning the source without touching the repository.
    generated = render(write=False).encode('utf-8')
    require(before == generated, 'BPMN XML и PlantUML расходятся. Требуется make render.')
    current = file_manifest()
    if opts.record:
        MANIFEST.write_text(json.dumps(current, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    else:
        require(MANIFEST.is_file(), 'Отсутствует manifest.json. Требуется make render.')
        require(json.loads(MANIFEST.read_text()) == current, 'Исходники или изображения изменились после сборки. Требуется make render.')
    print(f'BPMN: {counts[0]} узлов, {counts[1]} переходов; основные и запасные пути связаны.')
    print('C4: 1 система, 6 контейнеров, 6 компонентов ML-сервиса.')
    print('4 схемы: исходники, PNG, SVG и ссылки README согласованы.')

if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, ET.ParseError) as exc:
        print(f'Проверка остановлена: {exc}', file=sys.stderr)
        sys.exit(1)
