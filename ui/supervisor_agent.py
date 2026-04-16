"""
supervisor_agent.py
Agente supervisore: riceve task grandi, li scompone in subtask,
esegue ogni subtask con cam_agent.esegui_agente() e riprende
automaticamente se il worker raggiunge il limite turni.

LIMITAZIONI:
- Il worker (cam_agent) ha max 40 turni per subtask
- I subtask devono essere indipendenti e sequenziali
- Non adatto per task che richiedono accesso al DB SQLite live
  (usare Jules per quelli)
- Non adatto per task > 10 subtask (usa Jules per task molto grandi)
"""
import json, os, sys, time, glob, re


def esegui_supervisore(task_grande, max_subtask=8):
    _root = os.path.join(os.path.dirname(__file__), '..')
    _ui = os.path.dirname(__file__)
    for p in [_root, _ui]:
        if p not in sys.path:
            sys.path.insert(0, p)

    import cam_agent as _ca

    risultati = []
    history = []

    # Step 1: chiedi al worker di scomporre il task in subtask
    piano_prompt = (
        "Analizza questo task e scomponilo in subtask sequenziali piccoli.\n"
        "Rispondi SOLO con JSON valido, nessun testo prima o dopo:\n"
        '{"task_id":"nome_snake_case","subtask":['
        '{"step":1,"titolo":"...","prompt":"...istruzione precisa e autonoma..."}]}\n\n'
        f"TASK DA SCOMPORRE:\n{task_grande}"
    )

    risposta_piano = _ca.esegui_agente(piano_prompt, max_turns=5)

    piano = None
    try:
        testo = risposta_piano.get('risposta', '')
        match = re.search(r'\{.*\}', testo, re.DOTALL)
        if match:
            piano = json.loads(match.group())
    except Exception as e:
        return {
            'errore': f'Supervisore: piano non parsabile — {e}',
            'risposta': risposta_piano.get('risposta', '')
        }

    if not piano or not piano.get('subtask'):
        return {'errore': 'Supervisore: nessun subtask estratto'}

    task_id = piano.get('task_id', 'supervisor_task')
    subtasks = piano['subtask'][:max_subtask]

    # Step 2: esegui ogni subtask con ripresa automatica
    for subtask in subtasks:
        step_num = subtask.get('step', '?')
        titolo = subtask.get('titolo', f'Step {step_num}')
        prompt = subtask.get('prompt', '')

        # Aggiungi contesto dei passi precedenti
        if risultati:
            contesto = "\n\nPASSI GIA COMPLETATI:\n"
            for r in risultati[-3:]:
                contesto += f"- Step {r['step']} ({r['titolo']}): {r['esito']}\n"
            prompt_completo = prompt + contesto
        else:
            prompt_completo = prompt

        # Tenta il subtask con ripresa automatica (max 3 volte)
        for tentativo in range(3):
            result = _ca.esegui_agente(
                prompt_completo,
                history=history,
                max_turns=40
            )

            risposta = result.get('risposta', '')
            history = result.get('history', history)

            # Controlla se si e' fermato per limite turni
            if 'limite' in risposta.lower() and 'turni' in risposta.lower():
                # Estrai task_id dal messaggio e riprendi
                match_tid = re.search(r'`continua\s+(\S+)`', risposta)
                if match_tid:
                    tid = match_tid.group(1)
                    prompt_completo = f'continua {tid}'
                    time.sleep(2)
                    continue  # ritenta con continua
                else:
                    # Fallback: cerca checkpoint piu recente
                    cp_dir = os.path.join(_root, 'checkpoints')
                    cp_files = glob.glob(os.path.join(cp_dir, '*.json'))
                    if cp_files:
                        newest = max(cp_files, key=os.path.getmtime)
                        tid = os.path.basename(newest).replace('.json', '')
                        prompt_completo = f'continua {tid}'
                        time.sleep(2)
                        continue

            # Step completato (o fallito definitivamente)
            risultati.append({
                'step': step_num,
                'titolo': titolo,
                'esito': 'errore' if result.get('errore') else 'completato',
                'risposta': risposta[:300],
                'errore': result.get('errore')
            })
            break
        else:
            risultati.append({
                'step': step_num, 'titolo': titolo,
                'esito': 'fallito dopo 3 tentativi'
            })

    # Report finale
    completati = sum(1 for r in risultati if r['esito'] == 'completato')
    report = f"**Supervisore completato**\n\n"
    report += f"Task: `{task_id}`\n"
    report += f"Step completati: {completati}/{len(risultati)}\n\n"
    for r in risultati:
        icona = 'OK' if r['esito'] == 'completato' else 'FAIL'
        report += f"[{icona}] Step {r['step']}: {r['titolo']}\n"
        if r.get('errore'):
            report += f"   ! {r['errore'][:100]}\n"

    return {
        'risposta': report,
        'task_id': task_id,
        'risultati': risultati,
        'eseguito_da': 'claude',
        'modello': 'supervisor',
    }
