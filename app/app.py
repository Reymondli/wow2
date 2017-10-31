from flask import Flask, flash, redirect,\
                  render_template, request, url_for
import os
import time
import shutil
import boto3
from sqlalchemy import create_engine
from flask import session as login_session
from sqlalchemy.orm import sessionmaker
from database_setup import Base, User, Photo, salted
from werkzeug.utils import secure_filename
from wand.image import Image

UPLOAD_FOLDER = 'static/'
ALLOWED_EXTENSIONS = set(['txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'])

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.secret_key = 'super secret key'

engine = create_engine('mysql://ece1779:secret@172.31.40.82:3306/cca1', echo=False)
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# Helper functions to provide four transformations of image
def image_thumbnail(filename):
    destination = os.path.join('static/tmp', filename)
    with Image(filename=destination) as img:
        img.resize(270, 180)
        prefix = "thumbnail_"
        new_destination = os.path.join(
                                        'static/tmp',
                                        prefix + filename,
                                        )
        img.save(filename=new_destination)


def image_mirror(filename):
    destination = os.path.join('static/tmp', filename)
    with Image(filename=destination) as img:
        img.flop()
        prefix = "mirror_"
        new_destination = os.path.join(
                                        'static/tmp',
                                        prefix + filename,
                                        )
        img.save(filename=new_destination)


def image_grayscale(filename):
    destination = os.path.join('static/tmp', filename)
    with Image(filename=destination) as img:
        img.type = 'grayscale'
        prefix = "bw_"
        new_destination = os.path.join(
                                        'static/tmp',
                                        prefix + filename,
                                        )
        img.save(filename=new_destination)


def image_enhance(filename):
    destination = os.path.join('static/tmp', filename)
    with Image(filename=destination) as img:
        frequency = 3
        phase_shift = -90
        amplitude = 0.2
        bias = 0.7
        img.function('sinusoid', [frequency, phase_shift, amplitude, bias])
        prefix = "enhance_"
        new_destination = os.path.join(
                                        'static/tmp',
                                        prefix + filename,
                                        )
        img.save(filename=new_destination)


# Create route and function to display home page
@app.route('/')
def home():
    if not login_session.get('logged_in'):
        return render_template('login.html', login_session=login_session)
    else:
        return redirect(url_for('upload_file',
                                user_id=login_session['user_id']))


# Create route and function to display signup page
@app.route('/signup', methods=['GET', 'POST'])
def showSignup():
    if request.method == 'POST':
        login_session['username'] = str(request.form['username'])
        login_session['password'] = str(request.form['password'])

        if login_session['username'] == "" or login_session['password'] == "":
            flash("Username/Password can't be empty")
            return redirect(url_for('showSignup'))

        query = session.query(User).filter_by(
                                                username=(login_session['username']),
                                                )
        result = query.first()
        if result:
            flash("user already exists")
            return redirect(url_for('showSignup'))
        else:
            newUser = User(
                            username=login_session['username'],
                            password=login_session['password'],
                            )
            session.add(newUser)
            session.commit()
            user = session.query(User).filter_by(username=login_session['username']).one()
            login_session['logged_in'] = True
            login_session['user_id'] = user.id
            return redirect(url_for('upload_file', user_id=user.id))
    elif request.method == 'GET':
        return render_template('signup.html', login_session=login_session)


# Create route and function to display login page
@app.route('/login', methods=['POST'])
def do_admin_login():
    login_session['username'] = str(request.form['username'])
    login_session['password'] = str(request.form['password'])

    HASH_PASSWORD = salted(login_session['password'], login_session['username'])

    query = session.query(User).filter_by(
                                            username=login_session['username'],
                                            password=HASH_PASSWORD)
    result = query.first()
    if result:
        login_session['logged_in'] = True
        login_session['user_id'] = result.id
        return redirect(url_for('upload_file', user_id=result.id))
    else:
        flash('Incorrect username or password!')
        return render_template('login.html', login_session=login_session)


# Create route and function to display logout page
@app.route("/logout")
def logout():
    login_session['logged_in'] = False
    del login_session['username']
    del login_session['password']
    return redirect(url_for('home'))


# Create route and function to display user uploaded image and upload function
@app.route('/upload/<int:user_id>', methods=['GET', 'POST'])
def upload_file(user_id):
    user = session.query(User).filter_by(id=user_id).one()
    items = session.query(Photo).filter_by(user_id=user.id)
    if not login_session.get('logged_in') or user_id != login_session['user_id']:
        return render_template('login.html', login_session=login_session)
    if request.method == 'POST':
        # check if the post request has the file part
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        file = request.files['file']
        # if user does not select file, browser also
        # submit a empty part without filename
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            if not os.path.isdir('static/tmp'):
                os.makedirs('static/tmp')
            filename_raw = secure_filename(file.filename)
            filename = login_session['username'] + "_" + filename_raw
            file.save(os.path.join(
                                    app.config['UPLOAD_FOLDER'] +
                                    'tmp',
                                    filename))
            filePath = 'static/tmp'
            # Generate transformed images
            image_thumbnail(filename)
            image_mirror(filename)
            image_grayscale(filename)
            image_enhance(filename)

            # Upload  images to s3
            s3 = boto3.client('s3')

            s3_origin = filePath + '/' + filename
            s3_thumbnail = filePath + '/' + 'thumbnail_' + filename
            s3_transone = filePath + '/' + 'bw_' + filename
            s3_transtwo = filePath + '/' + 'mirror_' + filename
            s3_transthree = filePath + '/' + 'enhance_' + filename

            s3.upload_file(s3_origin, "cca2", 'origin_' + filename)
            s3.upload_file(s3_thumbnail, "cca2", 'thumbnail_' + filename)
            s3.upload_file(s3_transone, "cca2", 'bw_' + filename)
            s3.upload_file(s3_transtwo, "cca2", 'mirror_' + filename)
            s3.upload_file(s3_transthree, "cca2", 'enhance_' + filename)

            #Delete temporary folder
            shutil.rmtree('static/tmp')

            # Make s3 images public
            s3 = boto3.resource('s3')

            object_acl = s3.ObjectAcl('cca2', 'origin_' + filename)
            object_acl.put(ACL='public-read')

            object_acl = s3.ObjectAcl('cca2', 'thumbnail_' + filename)
            object_acl.put(ACL='public-read')

            object_acl = s3.ObjectAcl('cca2', 'bw_' + filename)
            object_acl.put(ACL='public-read')

            object_acl = s3.ObjectAcl('cca2', 'mirror_' + filename)
            object_acl.put(ACL='public-read')

            object_acl = s3.ObjectAcl('cca2', 'enhance_' + filename)
            object_acl.put(ACL='public-read')

            # Obtain url for public images
            url_origin = 'https://s3.amazonaws.com/cca2/' + 'origin_' + filename
            url_thumbnail = 'https://s3.amazonaws.com/cca2/' + 'thumbnail_' + filename
            url_transone = 'https://s3.amazonaws.com/cca2/' + 'bw_' + filename
            url_transtwo = 'https://s3.amazonaws.com/cca2/' + 'mirror_' + filename
            url_transthree = 'https://s3.amazonaws.com/cca2/' + 'enhance_' + filename

            # Store url into database
            newPhoto = Photo(
                            name=filename,
                            origin= url_origin,
                            thumbnail= url_thumbnail,
                            trans_one= url_transone,
                            trans_two= url_transtwo,
                            trans_three= url_transthree,
                            user_id=login_session['user_id'])
            session.add(newPhoto)
            flash('New Photo %s Successfully Uploaded' % filename)
            session.commit()

            # Set 1 sec delay for assuring database transaction completed
            time.sleep(1)
            return redirect(url_for('upload_file',
                                    user_id=user_id))

    else:
        return render_template(
                                'uploadtest.html',
                                items=items,
                                user_id=user_id,
                                username=user.username)


# Create route and function to display transformations for an image
@app.route('/photo/<int:user_id>/<int:photo_id>', methods=['GET'])
def photo_detail(user_id, photo_id):
    user = session.query(User).filter_by(id=user_id).one()
    items = session.query(Photo).filter_by(user_id=user_id, id=photo_id)
    if not login_session.get('logged_in') or user.id != login_session['user_id']:
        flash('Please login first')
        return render_template('login.html', login_session=login_session)
    else:
        return render_template('photo.html', items=items, user=user)


# Create route and function to delete a image and its transformations
@app.route('/photo/<int:user_id>/<int:photo_id>/delete', methods=['GET', 'POST'])
def photo_delete(user_id, photo_id):
    user = session.query(User).filter_by(id=user_id).one()
    items = session.query(Photo).filter_by(user_id=user.id)
    itemToDelete = session.query(Photo).filter_by(id=photo_id).one()
    if not login_session.get('logged_in') or user.id != login_session['user_id']:
        return render_template('login.html', login_session=login_session)
    if request.method == 'POST':
        # Delete images on s3
        client = boto3.client('s3')

        client.delete_object(Bucket='cca2', Key='origin_'+itemToDelete.name)
        client.delete_object(Bucket='cca2', Key='bw_'+itemToDelete.name)
        client.delete_object(Bucket='cca2', Key='mirror_'+itemToDelete.name)
        client.delete_object(Bucket='cca2', Key='enhance_'+itemToDelete.name)
        client.delete_object(Bucket='cca2', Key='thumbnail_'+itemToDelete.name)


        session.delete(itemToDelete)
        session.commit()
        flash("Photo Deleted")
        return redirect(url_for('upload_file', user_id=user_id))
    else:
        return render_template(
                                'deletephoto.html',
                                user_id=user_id,
                                items=items,
                                item=itemToDelete,
                                user=user)


# Create route and function for TA automatically upload image and populate account
@app.route('/ta', methods=['GET', 'POST'])
def taAccess():
    if request.method == 'POST':
        login_session['username'] = str(request.form['username'])
        login_session['password'] = str(request.form['password'])

        if login_session['username'] == "" or login_session['password'] == "":
            flash("Username/Password can't be empty")
            return redirect(url_for('taAccess'))

        query = session.query(User).filter_by(username=(login_session['username']))
        result = query.first()
        if result:
            flash("user already exists")
            return redirect(url_for('taAccess'))
        else:
            newUser = User(
                            username=login_session['username'],
                            password=login_session['password'],
                            )
            session.add(newUser)
            session.commit()
            user = session.query(User).filter_by(username=login_session['username']).one()
            login_session['logged_in'] = True
            login_session['user_id'] = user.id

        user_express = session.query(User).filter_by(id=login_session['user_id']).one()
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        file = request.files['file']
        # if user does not select file, browser also
        # submit a empty part without filename
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            if not os.path.isdir('static/tmp'):
                os.makedirs('static/tmp')
            filename_raw = secure_filename(file.filename)
            filename = login_session['username'] + "_" + filename_raw
            file.save(os.path.join(
                                    app.config['UPLOAD_FOLDER'] +
                                    'tmp',
                                    filename))
            filePath = 'static/tmp'
            image_thumbnail(filename)
            image_mirror(filename)
            image_grayscale(filename)
            image_enhance(filename)
            # Upload to s3
            s3 = boto3.client('s3')

            s3_origin = filePath + '/' + filename
            s3_thumbnail = filePath + '/' + 'thumbnail_' + filename
            s3_transone = filePath + '/' + 'bw_' + filename
            s3_transtwo = filePath + '/' + 'mirror_' + filename
            s3_transthree = filePath + '/' + 'enhance_' + filename

            s3.upload_file(s3_origin, "cca2", 'origin_' + filename)
            s3.upload_file(s3_thumbnail, "cca2", 'thumbnail_' + filename)
            s3.upload_file(s3_transone, "cca2", 'bw_' + filename)
            s3.upload_file(s3_transtwo, "cca2", 'mirror_' + filename)
            s3.upload_file(s3_transthree, "cca2", 'enhance_' + filename)

            shutil.rmtree('static/tmp')

            s3 = boto3.resource('s3')

            object_acl = s3.ObjectAcl('cca2', 'origin_' + filename)
            object_acl.put(ACL='public-read')

            object_acl = s3.ObjectAcl('cca2', 'thumbnail_' + filename)
            object_acl.put(ACL='public-read')

            object_acl = s3.ObjectAcl('cca2', 'bw_' + filename)
            object_acl.put(ACL='public-read')

            object_acl = s3.ObjectAcl('cca2', 'mirror_' + filename)
            object_acl.put(ACL='public-read')

            object_acl = s3.ObjectAcl('cca2', 'enhance_' + filename)
            object_acl.put(ACL='public-read')


            url_origin = 'https://s3.amazonaws.com/cca2/' + 'origin_' + filename
            url_thumbnail = 'https://s3.amazonaws.com/cca2/' + 'thumbnail_' + filename
            url_transone = 'https://s3.amazonaws.com/cca2/' + 'bw_' + filename
            url_transtwo = 'https://s3.amazonaws.com/cca2/' + 'mirror_' + filename
            url_transthree = 'https://s3.amazonaws.com/cca2/' + 'enhance_' + filename


            newPhoto = Photo(
                            name=filename,
                            origin= url_origin,
                            thumbnail= url_thumbnail,
                            trans_one= url_transone,
                            trans_two= url_transtwo,
                            trans_three= url_transthree,
                            user_id=login_session['user_id'])
            session.add(newPhoto)
            flash('New Photo %s Successfully Uploaded' % filename)
            session.commit()

            # Set 1 sec delay for assuring database transaction completed
            time.sleep(1)
            return redirect(url_for('upload_file', user_id=user_express.id))
    else:
        return render_template('ta.html', login_session=login_session)


if __name__ == "__main__":

    app.run(debug=True, host='localhost', port=5000)
