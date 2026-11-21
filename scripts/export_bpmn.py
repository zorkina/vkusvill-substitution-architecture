"""Build a PlantUML/DOT view from the BPMN model and its saved coordinates."""
from pathlib import Path
import json
import math
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
NS = {'bpmn': 'http://www.omg.org/spec/BPMN/20100524/MODEL',
      'bpmndi': 'http://www.omg.org/spec/BPMN/20100524/DI',
      'dc': 'http://www.omg.org/spec/DD/20100524/DC',
      'di': 'http://www.omg.org/spec/DD/20100524/DI'}

def q(s):
    return json.dumps(str(s), ensure_ascii=False)

def attrs(values):
    return ', '.join(f'{k}={q(v)}' for k, v in values.items())

def render(write=True):
    tree = ET.parse(ROOT / 'diagrams/01-process.bpmn')
    elements = {e.get('id'): e for e in tree.iter() if e.get('id')}
    bounds = {}
    labels = {}
    for s in tree.findall('.//bpmndi:BPMNShape', NS):
        b = s.find('dc:Bounds', NS)
        bounds[s.get('bpmnElement')] = tuple(float(b.get(k)) for k in ('x', 'y', 'width', 'height'))
        lb = s.find('bpmndi:BPMNLabel/dc:Bounds', NS)
        if lb is not None:
            labels[s.get('bpmnElement')] = tuple(float(lb.get(k)) for k in ('x', 'y', 'width', 'height'))

    lines = ['@startdot', 'digraph process {',
        'graph [layout=neato, maxiter=0, overlap=true, splines=false, inputscale=72, outputorder=nodesfirst, bgcolor="#FFFFFF", margin=0.15, pad=0.15];',
        'node [pin=true, fontname="DejaVu Sans", fontsize=18, color="#334155", penwidth=1.5, margin=0.06];',
        'edge [color="#475569", penwidth=1.6, arrowsize=0.9];']

    def draw(id, box, text='', **kw):
        x, y, w, h = box
        defaults = dict(pos=f'{x+w/2},{-y-h/2}!', width=w/72, height=h/72,
                        fixedsize='true', label=text)
        defaults.update(kw)
        if defaults.get('shape') == 'plaintext':
            defaults['fixedsize'] = 'false'
        lines.append(f'{id} [{attrs(defaults)}];')

    def stroke(id, points, color='#334155', width=1.4):
        """Draw a symbol as vectors, without relying on a font glyph."""
        for i, (x, y) in enumerate(points):
            draw(f'{id}_{i}', (x, y, 0, 0), shape='point', style='invis', width=0, height=0)
        for i in range(len(points)-1):
            settings = dict(arrowhead='none', color=color, penwidth=width)
            lines.append(f'{id}_{i} -> {id}_{i+1} [{attrs(settings)}];')

    def gear(id, cx, cy, radius):
        points = []
        for i in range(32):
            angle = 2 * math.pi * i / 32
            r = radius if i % 4 in (1, 2) else radius * 0.73
            points.append((cx + r*math.cos(angle), cy + r*math.sin(angle)))
        stroke(id+'_teeth', points + points[:1], width=1.1)
        draw(id+'_hub', (cx-1.8, cy-1.8, 3.6, 3.6), shape='circle', penwidth=1)

    def task_marker(id, kind, box):
        x, y, _, _ = box
        if kind == 'serviceTask':
            gear(id+'_gear1', x+16, y+14, 6.5)
            gear(id+'_gear2', x+25, y+22, 5.4)
        elif kind == 'userTask':
            draw(id+'_head', (x+14, y+7, 7, 7), shape='circle', penwidth=1.3)
            stroke(id+'_body', [(x+14,y+16),(x+11,y+18),(x+10,y+26),
                               (x+25,y+26),(x+24,y+18),(x+21,y+16),
                               (x+14,y+16)])
            stroke(id+'_arm1', [(x+14,y+20),(x+14,y+26)], width=1)
            stroke(id+'_arm2', [(x+21,y+20),(x+21,y+26)], width=1)

    def event_marker(id, timer, box):
        x, y, w, h = box
        cx, cy = x+w/2, y+h/2
        if timer:
            draw(id+'_clock', (cx-11,cy-11,22,22), shape='circle', penwidth=1)
            for i in range(8):
                a = i*math.pi/4
                stroke(id+f'_tick{i}', [(cx+8.3*math.cos(a),cy+8.3*math.sin(a)),
                                       (cx+10*math.cos(a),cy+10*math.sin(a))], width=1)
            stroke(id+'_hands', [(cx,cy-6),(cx,cy),(cx+5,cy+3)], width=1.6)
        else:
            bolt = [(-6,-10),(-2,1),(2,-3),(7,10),(2,0),(-1,4),(-6,-10)]
            stroke(id+'_error', [(cx+dx,cy+dy) for dx,dy in bolt], width=1.2)

    # The pool and lanes are rectangles; paths are routed with the BPMN DI waypoints.
    draw('title', (170, -35, 1520, 55), 'BPMN | ВкусВилл: замена одной отсутствующей позиции', shape='plaintext', fontsize=27, fontcolor='#0f3f3a')
    draw('subtitle', (260, 20, 1400, 40), 'От обнаружения отсутствия до изменения заказа и записи исхода', shape='plaintext', fontsize=17, fontcolor='#64748b')
    draw('Participant_Vkusvill', bounds['Participant_Vkusvill'], '', shape='box', style='filled', fillcolor='white', color='#475569')
    for id, color in [('Lane_Picker','#f8fafc'),('Lane_Service','#f8fafc'),('Lane_Model','#edf7f5')]:
        x,y,w,h = bounds[id]
        draw(id, (x,y,w,h), '', shape='box', style='filled', fillcolor=color, color='#cbd5e1', penwidth=1)
        draw(id+'_title', (x,y,w,45), elements[id].get('name'), shape='box', style='filled', fillcolor='#e2e8f0' if id != 'Lane_Model' else '#cce8e3', fontsize=21)
    draw('pool_title', (270,90,1400,30), elements['Participant_Vkusvill'].get('name'), shape='plaintext', fontsize=18)
    draw('Participant_Customer', bounds['Participant_Customer'], 'Покупатель\n[отдельный пул]', shape='box', style='filled', fillcolor='#f1f5f9', fontsize=19)

    for id, box in bounds.items():
        e = elements[id]
        kind = e.tag.rsplit('}',1)[1]
        name = e.get('name','')
        if kind in {'participant','lane'}:
            continue
        if kind in {'userTask','serviceTask','task'}:
            fill = '#cce8e3' if id == 'B04' else ('#fff0d8' if id == 'B05' else 'white')
            draw(id,box,'',shape='box',style='rounded,filled',fillcolor=fill)
            x,y,w,h=box
            text_width = w-20 if id == 'B10' else w
            text_size = 17 if id == 'B10' else 18
            draw(id+'_name',(x,y+20,text_width,h-20),name,shape='plaintext',fontsize=text_size)
            task_marker(id,kind,box)
        elif kind == 'startEvent':
            draw(id,box,'',shape='circle',style='filled',fillcolor='white',penwidth=1.8)
        elif kind == 'endEvent':
            draw(id,box,'',shape='circle',style='filled',fillcolor='white',penwidth=4)
        elif kind == 'exclusiveGateway':
            draw(id,box,'×',shape='diamond',style='filled',fillcolor='#fef3c7',fontsize=27)
        elif kind == 'boundaryEvent':
            timer = e.find('bpmn:timerEventDefinition',NS) is not None
            draw(id,box,'',shape='doublecircle',style='filled',fillcolor='white',penwidth=1.5)
            event_marker(id,timer,box)
        elif kind == 'dataStoreReference':
            draw(id,box,'Журнал\nрешений',shape='cylinder',style='filled',fillcolor='#e0f2fe',fontsize=18)
        elif kind == 'textAnnotation':
            txt=e.find('bpmn:text',NS).text
            x,y,w,h=box
            draw(id,(x+12,y,w-12,h),txt,shape='plaintext',fontsize=16)
            stroke(id+'_bracket',[(x+12,y),(x,y),(x,y+h),(x+12,y+h)],color='#94a3b8',width=1.2)
        else:
            raise ValueError(f'Unsupported BPMN element: {kind}')
        if id in labels and name:
            draw(id+'_label',labels[id],name,shape='plaintext',fontsize=15)

    for edge in tree.findall('.//bpmndi:BPMNEdge',NS):
        id = edge.get('bpmnElement')
        e = elements[id]
        kind = e.tag.rsplit('}',1)[1]
        points=[(float(p.get('x')),float(p.get('y'))) for p in edge.findall('di:waypoint',NS)]
        for i,(x,y) in enumerate(points):
            draw(f'{id}_p{i}', (x,y,0,0), '', shape='point', width=0, height=0, penwidth=0)
        for i in range(len(points)-1):
            settings = {'arrowhead': 'normal' if i==len(points)-2 else 'none'}
            if kind=='messageFlow':
                settings.update(style='dashed',arrowhead='onormal' if i==len(points)-2 else 'none')
                if i==0:settings.update(dir='both',arrowtail='odot')
            elif kind in {'dataOutputAssociation','association'}:
                settings.update(style='dotted',color='#64748b',arrowhead='vee' if kind=='dataOutputAssociation' and i==len(points)-2 else 'none')
            lines.append(f'{id}_p{i} -> {id}_p{i+1} [{attrs(settings)}];')
        label = edge.find('bpmndi:BPMNLabel/dc:Bounds',NS)
        name = e.get('name','')
        if kind=='dataOutputAssociation':name='Данные для обучения'
        if label is not None and name:
            box=tuple(float(label.get(k)) for k in ('x','y','width','height'))
            draw(id+'_label',box,name,shape='plaintext',fontsize=15)
        if kind=='sequenceFlow' and elements[e.get('sourceRef')].get('default')==id:
            x,y=points[0];nx,ny=points[1]
            # Default flow marker near the gateway.
            if abs(nx-x)>abs(ny-y):x += 13 if nx>x else -13
            else:y += 13 if ny>y else -13
            draw(id+'_default',(x-7,y-9,14,18),'/',shape='plaintext',fontsize=21)

    draw('legend',(270,2640,1400,170),
         'ОБОЗНАЧЕНИЯ\nКруг: начало; круг с толстой границей: конец; скругленный прямоугольник: задача.\nЧеловек в задаче: работа сборщика; шестеренки: действие сервиса.\nРомб ×: исключающая развилка или слияние; / на стрелке: путь по умолчанию.\nДвойной круг на границе задачи: прерывание по ошибке (молния) или сроку (часы).\nСплошная стрелка: порядок шагов; штриховая: сообщение между пулами; точечная: данные.\nБирюзовая задача: вызов модели; песочная: ручной запасной путь.',
         shape='box',style='filled',fillcolor='#f8fafc',color='#cbd5e1',fontsize=16)
    lines += ['}', '@enddot','']
    target=ROOT/'diagrams/01-process.puml'
    source='\n'.join(lines)
    if write:
        target.write_text(source,encoding='utf-8')
        print(f'PlantUML source: {target.name}')
    return source

if __name__=='__main__':
    render()
