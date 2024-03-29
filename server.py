from modules.reclamo import Reclamo
from modules.usuario import Usuario
from flask import render_template, redirect, url_for, flash, abort, session, request
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, login_required, current_user, logout_user
import pickle

from functools import wraps
from modules.forms import LoginForm, RegisterForm
from modules.config import app, db, login_manager
from modules.clasificador import Clasificador

admin_list = [1]

#creo la base de datos
with app.app_context():
    db.create_all()

# Flask-login también requiere definir una función "user_loader",
# dado un ID de usuario, devuelve el objeto usuario asociado.
@login_manager.user_loader  
def user_loader(user_id):
    print(user_id)
    return db.session.get(Usuario, user_id) 

# usuarios admin
def is_admin():
    if current_user.is_authenticated and current_user.id in admin_list:
        return True
    else:
        return False

# https://flask.palletsprojects.com/en/2.3.x/patterns/viewdecorators/
# decorador para restringir el acceso a una vista a usuarios administradores
def admin_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.id not in admin_list:
            return abort(403) # la función abort() permite devolver errores HTTP de forma sencilla
                              # 403 significa "Forbidden"
        return f(*args, **kwargs)
    return decorated_function

@app.route("/")
def home():

    if 'username' in session:
        username = session['username']
    else:
        username = 'Invitado'

    print(current_user)
    return render_template('home.html', user=username, logged_in=current_user.is_authenticated)

@app.route("/login", methods= ["GET", "POST"])
def login():
    login_form = LoginForm()
    # Acceso a la información ingresada en el formulario
    # cuando el usuario realiza el "submit".
    if login_form.validate_on_submit():
        #hacemos una consulta filtrando por email para
        #saber si hay un usuario registrado con ese email
        user = Usuario.query.filter_by(email=login_form.email.data).first()
        if not user:
            flash("That email does not exist, please try again")
        elif not check_password_hash(user.contrasena, login_form.password.data):
            flash("Password incorrect, please try again.")
        else:
            login_user(user)
            print(current_user)
            session['username'] = user.nombre_usuario
            print(session['username'])

            return redirect(url_for('welcome', username=user.nombre_usuario))
            #if is_admin():
                #return redirect(url_for('admin', username=user.nombre_usuario)) 
            #else:
                #return redirect(url_for('welcome', username=user.nombre_usuario))        
    return render_template('login.html', form=login_form)

@app.route('/error_page')
def error_page():
    return render_template('error_page.html')

@app.route("/register", methods= ["GET", "POST"])
def register():
    register_form = RegisterForm()
    # Acceso a la información ingresada en el formulario
    # cuando el usuario realiza el "submit".
    if register_form.validate_on_submit():
        # Verifico que no exista usuario con igual email
        if Usuario.query.filter_by(email=register_form.email.data).first():
            flash("You've already signed up with that email, log in instead!")
            return redirect(url_for('login'))
        # Si el registro es correcto, se crea un nuevo usuario en la db
        encripted_pass = generate_password_hash(
            password= register_form.password.data,
            method= 'pbkdf2:sha256',
            salt_length=8
        )
        new_user = Usuario(
            email = register_form.email.data,
            contrasena = encripted_pass, #register_form.password.data
            nombre_usuario = register_form.username.data,
            nombre = register_form.name.data,
            apellido = register_form.lastname.data,
            claustro = register_form.claustro.data
        )
        
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for("login"))
    return render_template('register.html', form=register_form)

# decoramos la vista con login_required para asegurar de que el usuario actual está conectado
# y autenticado antes de llamar a la función
@app.route("/welcome/<username>")
@login_required
def welcome(username):           
    return render_template('welcome.html', user=username)

# ruta para usuarios admin
@app.route("/admin/<username>")
@admin_only
def admin(username):           
    return render_template('admin.html', user=username)

# logout
@app.route("/logout")
def logout():   
    print(current_user)  
    logout_user()      
    print(current_user)
    session['username'] = 'Invitado' 
    return redirect(url_for('home'))

# Rutas para reclamos ---------------------------------------------------------------------------------------------
@app.route("/crear_reclamo", methods=['GET', 'POST'])
@login_required
def crear_reclamo():
    if request.method == 'POST':
        if Reclamo.query.filter_by(texto=request.form["texto"]).first() == None: 
            
            #creo el reclamo
            reclamo = Reclamo(
                id_usuario_creador = current_user.id,
                texto = request.form['texto']
            )
            db.session.add(reclamo)
            reclamo.adherentes.append(current_user)
            db.session.commit()
            
            #clasifico el reclamo
            text = [reclamo.texto]
            with open('./data/clasificador_svm.pkl', 'rb') as archivo:
                cls = pickle.load(archivo)

            lista = cls.clasificar(text)
            reclamo.depto = lista[0]
            db.session.commit()
            flash("El reclamo se creo exitosamente", 'success')
        else:
            flash("Ya existe un reclamo similar")
            
            #opcion adherirse a reclamo
        return redirect(url_for('welcome', username=current_user.nombre_usuario))
    return render_template('crear_reclamo.html', username=current_user.nombre_usuario)

@app.route('/listar_reclamos', methods=['GET', 'POST'])
def listar_reclamos():
    # Obtener todos los reclamos pendientes
    reclamos = Reclamo.query.filter_by(estado="Pendiente").all()

    # Aplicar filtro por departamento
    departamento_filtro = request.args.get('departamento')
    if departamento_filtro:
        reclamos = [r for r in reclamos if r.depto == departamento_filtro]

    return render_template('listar_reclamos.html', reclamos=reclamos, departamento_filtro=departamento_filtro)
  
  
@app.route('/mis_reclamos', methods=['GET', 'POST'])
@login_required #asegura que el usuario esté registrado
def mis_reclamos():
    reclamos_usuario = Reclamo.query.filter_by(id_usuario_creador=current_user.id).all()
    return render_template('mis_reclamos.html', reclamos=reclamos_usuario)


#-----------------------------------------------------------------------------------

# Ruta para ayuda
@app.route('/ayuda', methods=['GET', 'POST'])
@login_required
def ayuda():
    if request.method == 'POST':
        # Process
        pass
    return render_template('ayuda.html')



if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0")