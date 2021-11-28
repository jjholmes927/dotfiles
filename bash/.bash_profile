#split everything out into separate files and sourced them
for file in ~/.profile.d/*
do
  source $file
done
