# app.py (Versão PRO)

import os
import csv
import io
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, cast, Date
from datetime import datetime

# --- CONFIGURAÇÃO ---
app = Flask(__name__)

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'estoque.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'sua-chave-secreta-ainda-mais-segura'

db = SQLAlchemy(app)

# --- MODELOS DO BANCO DE DADOS (sem mudanças) ---

class Produto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    categoria = db.Column(db.String(50), nullable=False)
    preco = db.Column(db.Float, nullable=False)
    quantidade_estoque = db.Column(db.Integer, default=0)
    estoque_minimo = db.Column(db.Integer, default=5)

    def to_dict(self):
        return {'id': self.id, 'codigo': self.codigo, 'nome': self.nome, 'categoria': self.categoria, 'preco': self.preco, 'quantidade_estoque': self.quantidade_estoque, 'estoque_minimo': self.estoque_minimo}

class Movimentacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    produto_id = db.Column(db.Integer, db.ForeignKey('produto.id', ondelete='CASCADE'), nullable=False)
    tipo = db.Column(db.String(10), nullable=False)
    quantidade = db.Column(db.Integer, nullable=False)
    data = db.Column(db.DateTime, default=func.now())
    produto = db.relationship('Produto', backref=db.backref('movimentacoes', lazy=True, cascade="all, delete-orphan"))

# --- ROTAS DA APLICAÇÃO ---

@app.context_processor
def inject_categorias():
    categorias_tuplas = db.session.query(Produto.categoria).distinct().all()
    categorias = sorted([c[0] for c in categorias_tuplas])
    return dict(categorias_menu=categorias)

@app.route('/')
def index():
    produtos = Produto.query.order_by(Produto.nome).all()
    
    # Cálculos para o Dashboard
    total_produtos = len(produtos)
    total_itens_estoque = db.session.query(func.sum(Produto.quantidade_estoque)).scalar() or 0
    valor_total_estoque = db.session.query(func.sum(Produto.quantidade_estoque * Produto.preco)).scalar() or 0
    alertas_estoque_count = sum(1 for p in produtos if p.quantidade_estoque <= p.estoque_minimo)

    # Dados para o gráfico de distribuição de estoque por categoria
    dist_estoque = db.session.query(
        Produto.categoria, 
        func.sum(Produto.quantidade_estoque)
    ).group_by(Produto.categoria).order_by(func.sum(Produto.quantidade_estoque).desc()).all()
    
    chart_labels = [item[0] for item in dist_estoque]
    chart_data = [item[1] for item in dist_estoque]

    return render_template('index.html', 
                           produtos=produtos, 
                           total_produtos=total_produtos,
                           total_itens_estoque=total_itens_estoque,
                           valor_total_estoque=valor_total_estoque,
                           alertas_estoque_count=alertas_estoque_count,
                           chart_labels=chart_labels,
                           chart_data=chart_data)

@app.route('/produto/<int:id>')
def produto_detalhe(id):
    produto = Produto.query.get_or_404(id)
    movimentacoes_produto = Movimentacao.query.filter_by(produto_id=id).order_by(Movimentacao.data.desc()).all()
    return render_template('produto_detalhe.html', produto=produto, movimentacoes=movimentacoes_produto)

# --- ROTAS DE CRUD (sem grandes mudanças, apenas redirecionamentos) ---
@app.route('/produto/novo', methods=['POST'])
def novo_produto():
    codigo_existente = Produto.query.filter_by(codigo=request.form['codigo']).first()
    if codigo_existente:
        flash(f"Erro: O código '{request.form['codigo']}' já está cadastrado!", 'danger')
        return redirect(url_for('index'))
    novo = Produto(codigo=request.form['codigo'], nome=request.form['nome'], categoria=request.form['categoria'], preco=float(request.form['preco']), quantidade_estoque=int(request.form['quantidade_estoque']), estoque_minimo=int(request.form['estoque_minimo']))
    db.session.add(novo)
    db.session.commit()
    flash('Produto cadastrado com sucesso!', 'success')
    return redirect(url_for('index'))

@app.route('/produto/editar/<int:id>', methods=['POST'])
def editar_produto(id):
    produto = Produto.query.get_or_404(id)
    novo_codigo = request.form['codigo']
    codigo_existente = Produto.query.filter(Produto.codigo == novo_codigo, Produto.id != id).first()
    if codigo_existente:
        flash(f"Erro: O código '{novo_codigo}' já pertence a outro produto!", 'danger')
        return redirect(url_for('index'))
    produto.codigo, produto.nome, produto.categoria, produto.preco, produto.quantidade_estoque, produto.estoque_minimo = novo_codigo, request.form['nome'], request.form['categoria'], float(request.form['preco']), int(request.form['quantidade_estoque']), int(request.form['estoque_minimo'])
    db.session.commit()
    flash('Produto atualizado com sucesso!', 'success')
    return redirect(request.referrer or url_for('index'))

@app.route('/produto/excluir/<int:id>', methods=['POST'])
def excluir_produto(id):
    produto = Produto.query.get_or_404(id)
    db.session.delete(produto)
    db.session.commit()
    flash(f'O produto "{produto.nome}" foi excluído com sucesso.', 'success')
    return redirect(url_for('index'))

@app.route('/produto/dados/<int:id>', methods=['GET'])
def get_dados_produto(id):
    produto = Produto.query.get_or_404(id)
    return jsonify(produto.to_dict())

@app.route('/movimentar', methods=['POST'])
def movimentar_estoque():
    produto_id = int(request.form['produto_id'])
    tipo = request.form['tipo_movimentacao']
    quantidade = int(request.form['quantidade'])
    produto = Produto.query.get_or_404(produto_id)
    if tipo == 'entrada':
        produto.quantidade_estoque += quantidade
        flash(f'{quantidade} unidades de "{produto.nome}" adicionadas ao estoque.', 'success')
    elif tipo == 'saida':
        if produto.quantidade_estoque >= quantidade:
            produto.quantidade_estoque -= quantidade
            flash(f'{quantidade} unidades de "{produto.nome}" removidas do estoque.', 'info')
        else:
            flash(f'Estoque insuficiente para "{produto.nome}". Apenas {produto.quantidade_estoque} disponíveis.', 'danger')
            return redirect(request.referrer or url_for('index'))
    movimentacao = Movimentacao(produto_id=produto_id, tipo=tipo, quantidade=quantidade)
    db.session.add(movimentacao)
    db.session.commit()
    return redirect(request.referrer or url_for('index'))

# --- ROTAS DE RELATÓRIO COM FILTROS E EXPORTAÇÃO ---

@app.route('/relatorio', methods=['GET'])
def relatorio():
    # Pega os parâmetros do filtro da URL
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    tipo_mov = request.args.get('tipo_mov')

    query = Movimentacao.query

    # Aplica os filtros se eles existirem
    if start_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        query = query.filter(cast(Movimentacao.data, Date) >= start_date)
    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        query = query.filter(cast(Movimentacao.data, Date) <= end_date)
    if tipo_mov and tipo_mov in ['entrada', 'saida']:
        query = query.filter(Movimentacao.tipo == tipo_mov)

    movimentacoes = query.order_by(Movimentacao.data.desc()).all()
    
    return render_template('relatorio.html', 
                           movimentacoes=movimentacoes,
                           start_date=start_date_str,
                           end_date=end_date_str,
                           tipo_mov=tipo_mov)

@app.route('/relatorio/exportar')
def exportar_relatorio():
    # Pega os mesmos filtros da rota de relatório
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    tipo_mov = request.args.get('tipo_mov')

    query = Movimentacao.query

    if start_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        query = query.filter(cast(Movimentacao.data, Date) >= start_date)
    if end_date_str:
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        query = query.filter(cast(Movimentacao.data, Date) <= end_date)
    if tipo_mov and tipo_mov in ['entrada', 'saida']:
        query = query.filter(Movimentacao.tipo == tipo_mov)

    movimentacoes = query.order_by(Movimentacao.data.desc()).all()

    # Gera o CSV em memória
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Escreve o cabeçalho
    writer.writerow(['ID', 'Data', 'Produto', 'Código', 'Categoria', 'Tipo', 'Quantidade'])
    
    # Escreve os dados
    for mov in movimentacoes:
        writer.writerow([
            mov.id, 
            mov.data.strftime('%Y-%m-%d %H:%M:%S'), 
            mov.produto.nome, 
            mov.produto.codigo,
            mov.produto.categoria,
            mov.tipo,
            mov.quantidade
        ])
    
    output.seek(0)
    
    return Response(output,
                    mimetype="text/csv",
                    headers={"Content-Disposition": "attachment;filename=relatorio_movimentacoes.csv"})

# --- INICIALIZAÇÃO ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5001)